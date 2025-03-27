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


@frappe.whitelist()
def sync_orders_from_date():
    """
    Sync Shopify orders from 23rd of the current month
    """
    try:
        # Construct the date string in ISO format for the 23rd of current month
        current_month = now()[:7]  # Gets YYYY-MM
        start_date = f"{current_month}-23T00:00:00Z"

        base_url = "https://doeraa.myshopify.com/admin/api/2021-04/orders.json"
        headers = {
            "X-Shopify-Access-Token": api_key,
        }

        # Add created_at_min parameter to filter orders
        url = f"{base_url}?created_at_min={start_date}&limit=250"

        orders = []
        while url:
            try:
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                response_data = response.json()
                orders.extend(response_data.get("orders", []))

                # Get the 'Link' header for pagination
                link_header = response.headers.get("Link")
                if link_header:
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

        # Create sales orders from the filtered orders
        sales_orders = create_sales_order(orders)
        return (
            f"{len(sales_orders)} Sales Orders created successfully from {start_date}!"
        )

    except Exception as e:
        frappe.log_error(f"Error during Shopify order sync from date: {e}")
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
            # Check if sales order exists
            if frappe.db.exists("Sales Order", {"shopify_order_id": order.get("id")}):
                continue

            customer_data = order.get("customer")
            if not customer_data:
                frappe.log_error(f"No customer data for order {order.get('id')}")
                continue

            customer_name = (
                f"{customer_data.get('first_name')} {customer_data.get('last_name')}"

            )
            customer_id = customer_data.get("id")
            customer = create_customer(customer_name, customer_id)

            # If customer creation failed and returned Guest Customer, skip this order
            if customer == "Guest Customer":
                frappe.log_error(
                    f"Failed to create customer for order {order.get('id')}"
                )
                continue

            address = get_address(order, customer)
            if not address:
                # Create a default billing address if address creation fails
                address = create_default_address(customer)

            items = get_items(order)
            if not items:
                frappe.log_error(f"No items found for order {order.get('id')}")
                continue

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
                    "taxes": get_taxes(order),
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

            sales_order.flags.ignore_mandatory = True
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


def create_default_address(customer_name):
    """Create a default billing address for the customer"""
    address_title = f"{customer_name}-Billing-Default"

    if frappe.db.exists("Address", {"address_title": address_title}):
        return frappe.get_doc("Address", {"address_title": address_title}).name

    try:
        address = frappe.get_doc(
            {
                "doctype": "Address",
                "address_title": address_title,
                "address_type": "Billing",
                "address_line1": "Default Address",
                "city": "Default City",
                "state": "Gujarat",  # Default to Gujarat for proper tax handling
                "country": "India",
                "is_primary_address": 1,
                "is_shipping_address": 1,
                "links": [{"link_doctype": "Customer", "link_name": customer_name}],
            }
        )

        address.flags.ignore_mandatory = True
        address.insert(ignore_permissions=True)
        frappe.db.commit()
        return address.name
    except Exception as e:
        frappe.log_error(
            f"Error creating default address for customer {customer_name}: {str(e)}"
        )
        return None


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

    # Get shipping/billing address to determine tax structure
    shipping_address = order.get("shipping_address", {})
    billing_address = order.get("billing_address", {})
    customer_state = (billing_address or shipping_address).get("province", "")

    # Default tax rates
    cgst_rate = 2.5
    sgst_rate = 2.5
    igst_rate = 5.0

    # For orders within Gujarat, apply CGST + SGST
    if customer_state.lower() == "gujarat":
        taxes.extend(
            [
                {
                    "charge_type": "On Net Total",
                    "account_head": "Output Tax CGST - DPL",
                    "cost_center": "Main - DPL",
                    "rate": cgst_rate,
                    "description": f"CGST @ {cgst_rate}%",
                    "included_in_print_rate": tax_included,
                },
                {
                    "charge_type": "On Net Total",
                    "account_head": "Output Tax SGST - DPL",
                    "cost_center": "Main - DPL",
                    "rate": sgst_rate,
                    "description": f"SGST @ {sgst_rate}%",
                    "included_in_print_rate": tax_included,
                },
            ]
        )
    else:
        # For orders outside Gujarat, apply IGST
        taxes.append(
            {
                "charge_type": "On Net Total",
                "account_head": "Output Tax IGST - DPL",
                "cost_center": "Main - DPL",
                "rate": igst_rate,
                "description": f"IGST @ {igst_rate}%",
                "included_in_print_rate": tax_included,
            }
        )

    return taxes


def create_customer(customer_name, customer_id=None):
    # Clean the customer name to remove any problematic characters
    clean_name = (
        customer_name.strip().replace('"', "").replace("'", "").replace(".", "")
    )

    if not clean_name:
        clean_name = "Guest Customer"

    try:
        # Check if customer exists
        if frappe.db.exists("Customer", {"shopify_customer_id": customer_id}):
            customer = frappe.get_doc("Customer", {"shopify_customer_id": customer_id})
            return customer.name

        # Create new customer
        customer = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": clean_name,
                "customer_type": "Individual",
                "customer_group": "Individual",
                "territory": "India",
                "gst_category": "Unregistered",
                "shopify_customer_id": customer_id,
            }
        )

        customer.flags.ignore_mandatory = True
        customer.flags.ignore_permissions = True
        customer.insert(ignore_permissions=True, ignore_mandatory=True)
        frappe.db.commit()
        return customer.name

    except Exception as e:
        frappe.log_error(f"Error creating customer {clean_name}: {str(e)}")
        # Create a fallback customer name with timestamp
        fallback_name = f"Customer-{now().replace(' ', '-').replace(':', '-')}"
        try:
            customer = frappe.get_doc(
                {
                    "doctype": "Customer",
                    "customer_name": fallback_name,
                    "customer_type": "Individual",
                    "customer_group": "Individual",
                    "territory": "India",
                    "gst_category": "Unregistered",
                    "naming_series": "CUST-.YYYY.-",
                }
            )
            customer.flags.ignore_mandatory = True
            customer.flags.ignore_permissions = True
            customer.insert(ignore_permissions=True, ignore_mandatory=True)
            frappe.db.commit()
            return fallback_name
        except:
            return "Guest Customer"


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
