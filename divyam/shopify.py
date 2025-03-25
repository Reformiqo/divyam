from frappe.utils.data import cint
import requests
import frappe
from frappe.utils import getdate, now, flt

api_key = frappe.local.conf.shopify_api_key


@frappe.whitelist()
def set_shopify(limit=250):
    base_url = "https://doeraa.myshopify.com/admin/api/2021-04/orders.json"
    headers = {
        "X-Shopify-Access-Token": api_key,
    }
    orders = []
    url = f"{base_url}?limit={limit}"
    while url:
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Raise an exception for 4xx or 5xx status codes
            response_data = response.json()
            orders.extend(response_data.get("orders", []))

            # Get the 'Link' header from the response headers
            link_header = response.headers.get("Link")
            if link_header:
                # Parse the 'Link' header to find the next page URL
                links = link_header.split(",")
                next_url = None
                for link in links:
                    if 'rel="next"' in link:
                        next_url = link[link.find("<") + 1 : link.find(">")]
                        break
                url = next_url
            else:
                url = None
        except requests.exceptions.RequestException as e:
            frappe.log_error(f"Error fetching Shopify data: {e}")
            break
    return orders


@frappe.whitelist()
def get_single_shopify_data(order_id):
    base_url = f"https://doeraa.myshopify.com/admin/api/2021-04/orders/{order_id}.json"
    headers = {"X-Shopify-Access-Token": api_key}
    try:
        response = requests.get(base_url, headers=headers)
        response.raise_for_status()
        order_data = response.json().get("order")
        return order_data
    except requests.exceptions.RequestException as e:
        frappe.log_error(f"Error fetching Shopify data: {e}")
        return e


@frappe.whitelist()
def get_shopify_data():

    base_url = "https://doeraa.myshopify.com/admin/api/2021-04/orders.json"
    headers = {"X-Shopify-Access-Token": api_key}
    orders = []
    # # All orders except draft
    url = f"{base_url}?limit=250"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    orders = response.json()

    # remove duplicate items from the sales order

    return create_sales_order(orders.get("orders", []))


@frappe.whitelist()
def enqueue_sync_shopify_orders():
    frappe.enqueue(sync_shopify_orders, queue="long")
    return "Enqueued Shopify Order Sync"


@frappe.whitelist()
def sync_shopify_orders(limit=1):
    """
    Manually trigger the synchronization of Shopify orders and create Sales Orders in the system.
    """
    try:
        shopify_orders = set_shopify(limit)
        sales_orders = create_sales_order(shopify_orders)
        return f"{len(sales_orders)} Sales Orders created successfully!"
    except Exception as e:
        # Log and notify the user about any errors during synchronization
        frappe.log_error(f"Error during Shopify order sync: {e}")
        frappe.throw(f"An error occurred while syncing Shopify orders: {e}")


def calculate_discount(order):
    total_discount = 0

    # Get discount from discount codes
    discount_codes = order.get("discount_codes", [])
    if discount_codes:
        for discount_code in discount_codes:
            if discount_code.get("type") == "fixed_amount":
                total_discount += float(discount_code.get("amount", 0))
            elif discount_code.get("type") == "percentage":
                # For percentage discounts, we need to calculate the amount
                percentage = float(discount_code.get("amount", 0))
                subtotal = float(order.get("subtotal_price", 0))
                total_discount += (percentage / 100) * subtotal

    # Add any additional discounts from the order
    total_discount += float(order.get("total_discounts", 0))

    return total_discount


def create_sales_order(orders):
    sales_order_names = []
    for order in orders:
        try:
            # Check if sales order exists; if not, then create
            if frappe.db.exists("Sales Order", {"shopify_order_id": order.get("id")}):
                continue

            customer_data = order.get("customer")
            if not customer_data:
                frappe.log_error(f"No customer data for order {order.get('id')}")
                continue

            customer_name = (
                f"{customer_data.get('first_name')} {customer_data.get('last_name')}"
            )
            customer = create_customer(customer_name)
            address = get_address(order, customer_name)
            items = get_items(order)
            taxes = get_taxes(order)

            # Calculate total discount
            discount_amount = calculate_discount(order)

            sales_order = frappe.get_doc(
                {
                    "doctype": "Sales Order",
                    "company": "Doeraa Private Limited",
                    "customer": customer,
                    "customer_address": address,
                    "items": items,
                    "tax_category": get_tax_category(order),
                    "taxes": taxes,
                    "delivery_date": now(),
                    "transaction_date": getdate(order.get("created_at")),
                    "shopify_order_id": order.get("id"),
                    "shopify_order_number": order.get("name"),
                    "apply_discount_on": "Net Total",
                    "discount_amount": discount_amount,
                    "additional_discount_percentage": 0,
                    "payment_schedule": [],
                    "status": "Draft",
                }
            )

            frappe.flags.ignore_validate = True
            sales_order.insert(ignore_permissions=True)

            # Add shipping charges if any
            create_shipping_charges(order)

            frappe.db.commit()
            sales_order_names.append(sales_order.name)

        except Exception as e:
            frappe.log_error(
                f"Error creating sales order for Shopify order {order.get('id')}: {str(e)}"
            )
            continue

    return sales_order_names


def get_tax_category(order):
    # Try billing address first, then shipping address
    province = (
        order.get("billing_address", {}) or order.get("shipping_address", {})
    ).get("province")

    # Default to Out-state if no province found
    if not province:
        frappe.log_error(
            f"No province found in order {order.get('id')}, defaulting to Out-state"
        )
        return "Out-state"

    return "In-state" if province == "Gujarat" else "Out-state"


@frappe.whitelist()
def get_items(order):
    order_items = order.get("line_items", [])
    items = []

    for item in order_items:
        # Generate item code from name if sku is null
        item_code = item.get("sku") or item.get("name")
        if not item_code:
            frappe.log_error(
                f"No SKU or name found for item in order {order.get('id')}"
            )
            continue

        # Check if item exists; if not, then create
        if not frappe.db.exists("Item", item_code):
            create_item(item_code, item.get("name"))

        items.append(
            {
                "item_code": item_code,
                "item_name": item.get("name")[:140],
                "rate": item.get("price"),
                "qty": item.get("quantity"),
                "warehouse": "Finished Goods - DPL",
                "delivery_date": now(),
                "uom": "Meter",
                "gst_treatment": "Taxable",
            }
        )
    return items


def create_item(item_code, item_name):
    try:
        item = frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": item_code,
                "item_name": item_name[:140] if item_name else item_code,
                "item_group": "Products",
                "gst_hsn_code": "998821",
                "uom": "Meter",
                "is_stock_item": 1,
                "include_item_in_manufacturing": 0,
                "stock_uom": "Meter",
            }
        )
        item.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(f"Error creating item {item_code}: {e}")
        raise


def get_taxes(order):
    taxes = []
    tax_included = order.get("taxes_included", False)
    tax_lines = order.get("tax_lines", [])

    # If there are specific tax lines from Shopify, use those
    if tax_lines:
        for tax_line in tax_lines:
            tax_rate = float(tax_line.get("rate", 0)) * 100  # Convert to percentage
            tax_title = tax_line.get("title", "")

            if "IGST" in tax_title:
                account_head = "Output Tax IGST - DPL"
            elif "CGST" in tax_title:
                account_head = "Output Tax CGST - DPL"
            elif "SGST" in tax_title:
                account_head = "Output Tax SGST - DPL"
            else:
                # Default to IGST for other cases
                account_head = "Output Tax IGST - DPL"

            taxes.append(
                {
                    "charge_type": "On Net Total",
                    "account_head": account_head,
                    "cost_center": "Main - DPL",
                    "rate": tax_rate,
                    "description": f"{tax_title} - {tax_rate}%",
                    "included_in_print_rate": tax_included,
                }
            )
    else:
        # Fallback to default tax structure based on province
        tax_category = get_tax_category(order)
        if tax_category == "Out-state":
            taxes.append(
                {
                    "charge_type": "On Net Total",
                    "account_head": "Output Tax IGST - DPL",
                    "cost_center": "Main - DPL",
                    "rate": 5,
                    "description": "IGST - 5.00%",
                    "included_in_print_rate": tax_included,
                }
            )
        else:
            taxes.append(
                {
                    "charge_type": "On Net Total",
                    "account_head": "Output Tax CGST - DPL",
                    "cost_center": "Main - DPL",
                    "rate": 2.5,
                    "description": "CGST - 2.50%",
                    "included_in_print_rate": tax_included,
                }
            )
            taxes.append(
                {
                    "charge_type": "On Net Total",
                    "account_head": "Output Tax SGST - DPL",
                    "cost_center": "Main - DPL",
                    "rate": 2.5,
                    "description": "SGST - 2.50%",
                    "included_in_print_rate": tax_included,
                }
            )

    return taxes


def create_customer(customer_name):
    if frappe.db.exists("Customer", {"customer_name": customer_name}):
        customer = frappe.get_doc("Customer", {"customer_name": customer_name})
    else:
        try:
            customer = frappe.get_doc(
                {
                    "doctype": "Customer",
                    "customer_name": customer_name,
                    "customer_type": "Individual",
                    "customer_group": "Individual",
                    "territory": "India",
                    "gst_category": "Unregistered",
                }
            )
            customer.insert(ignore_permissions=True)
            frappe.db.commit()
        except Exception as e:
            frappe.log_error(f"Error creating customer {customer_name}: {str(e)}")
            raise
    return customer.name


def get_address(order, customer_name):
    shipping_address = order.get("shipping_address")
    billing_address = order.get("billing_address")

    if not shipping_address and not billing_address:
        return None

    # Use billing address if available, otherwise use shipping address
    address_data = billing_address or shipping_address

    # Create a unique address title that includes customer reference
    address_title = f"{customer_name}-Billing"

    if frappe.db.exists("Address", {"address_title": address_title}):
        customer_address = frappe.get_doc("Address", {"address_title": address_title})
    else:
        customer_address = frappe.get_doc(
            {
                "doctype": "Address",
                "address_title": address_title,
                "address_type": "Billing",
                "address_line1": address_data.get("address1")[:140],
                "address_line2": address_data.get("address2"),
                "city": address_data.get("city"),
                "state": address_data.get("province"),
                "country": address_data.get("country"),
                "pincode": address_data.get("zip"),
                "phone": address_data.get("phone"),
                "email_id": order.get("contact_email"),
                "is_primary_address": 1,
                "is_shipping_address": 1,
                "links": [{"link_doctype": "Customer", "link_name": customer_name}],
            }
        )

        try:
            customer_address.insert(ignore_permissions=True)
            frappe.db.commit()
        except Exception as e:
            frappe.log_error(
                f"Error creating address for customer {customer_name}: {str(e)}"
            )
            return None

    return customer_address.name


@frappe.whitelist()
def taxees():
    order_id = "5453587153150"
    base_url = f"https://doeraa.myshopify.com/admin/api/2021-04/orders/{order_id}.json"
    headers = {"X-Shopify-Access-Token": api_key}
    try:
        response = requests.get(base_url, headers=headers)
        response.raise_for_status()
        order_data = response.json().get("order")
        tax_lines = order_data.get("tax_lines", [])
        tax_included = order_data.get("taxes_included")
        return {"tax_lines": tax_lines, "tax_included": tax_included}
    except requests.exceptions.RequestException as e:
        frappe.log_error(f"Error fetching Shopify data: {e}")
        return "Error"


@frappe.whitelist()
def update_shipping_carhges(orders):
    sales_orders = []
    for order in orders.get("orders", []):
        try:
            sales_order = frappe.get_doc(
                "Sales Order", {"shopify_order_id": order.get("id"), "docstatus": 0}
            )
            shipping_lines = order.get("shipping_lines", [])
            if not shipping_lines:
                continue

            if shipping_lines:
                charge = shipping_lines[0].get("price")
                if float(charge) > 0:
                    append_item(
                        sales_order,
                        "SHIPPING CHARGES",
                        "SHIPPING CHARGES",
                        charge,
                        1,
                        "Finished Goods - DPL",
                        getdate(now()),
                        "Nos",
                    )
                sales_orders.append(charge)

        except Exception as e:
            frappe.log_error(f"Error updating shipping charges: {e}")
    return sales_orders


def append_item(
    sales_order, item_code, item_name, rate, qty, warehouse, delivery_date, uom
):
    sales_order.append(
        "items",
        {
            "item_code": item_code,
            "item_name": item_name,
            "rate": rate,
            "qty": qty,
            "warehouse": warehouse,
            "delivery_date": delivery_date,
            "uom": uom,
        },
    )
    sales_order.save()
    frappe.db.commit()


@frappe.whitelist()
def shipping_charges():
    base_url = "https://doeraa.myshopify.com/admin/api/2021-04/orders.json"
    headers = {"X-Shopify-Access-Token": api_key}
    orders = []
    # # All orders except draft
    url = f"{base_url}?limit=250"
    while url:
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Raise an exception for 4xx or 5xx status codes
            response_data = response.json()
            orders.extend(response_data.get("orders", []))

            # Get the 'Link' header from the response headers
            link_header = response.headers.get("Link")
            if link_header:
                # Parse the 'Link' header to find the next page URL
                links = link_header.split(",")
                next_url = None
                for link in links:
                    if 'rel="next"' in link:
                        next_url = link[link.find("<") + 1 : link.find(">")]
                        break
                url = next_url
            else:
                url = None
        except requests.exceptions.RequestException as e:
            frappe.log_error(f"Error fetching Shopify data: {e}")
            break
    return update_shipping_carhges({"orders": orders})


def remove_duplicate_items(sales_order):
    items = sales_order.get("items")
    item_codes = []
    for item in items:
        if item.get("item_code") not in item_codes:
            item_codes.append(item.get("item_code"))
        else:
            sales_order.remove(item)
    return sales_order


@frappe.whitelist()
def remove_item():
    # get last 10 orders
    # orders = frappe.get_all("Sales Order", filters={"docstatus": 0}, order_by="creation desc", limit=10)
    orders = frappe.get_all("Sales Order", filters={"docstatus": 0})
    for order in orders:
        sales_order_doc = frappe.get_doc("Sales Order", order.name)
        sales_order = remove_duplicate_items(sales_order_doc)
        sales_order.save()
        frappe.db.commit()
        frappe.msgprint("Items removed successfully")
    return "Items removed successfully"


# create discount
@frappe.whitelist()
def create_discount():
    orders = set_shopify(limit=250)
    discount_codes = []
    for o in orders:
        discount_code = o.get("discount_codes", [])
        if discount_code:
            discount = discount_code[0].get("amount")
            discount_codes.append(discount)
            doc = frappe.get_doc(
                "Sales Order", {"shopify_order_id": o.get("id"), "docstatus": 0}
            )
            doc.apply_discount_on = "Grand Total"
            doc.discount_amount = cint(discount)
            doc.save()
            frappe.db.commit()
    return discount_codes


def create_shipping_charges(order):
    doc = frappe.get_doc("Sales Order", {"shopify_order_id": order.get("id")})
    shipping_lines = order.get("shipping_lines", [])
    if shipping_lines:
        charge = shipping_lines[0].get("price")
        if float(charge) > 0:
            append_item(
                doc,
                "SHIPPING CHARGES",
                "SHIPPING CHARGES",
                charge,
                1,
                "Finished Goods - DPL",
                getdate(now()),
                "Nos",
            )
            doc.save()
            frappe.db.commit()
