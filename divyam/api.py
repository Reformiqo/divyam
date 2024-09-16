#create sales order from shopify
import frappe
from frappe.utils import getdate
@frappe.whitelist(allow_guest=True)
def create_order(data):
    data = frappe.parse_json(data)
    create_sales_order(data)
    customer_name = data.get("customer").get("first_name") + data.get("customer").get("last_name")
    get_address(data, customer_name)
    return "Order Created"

def create_customer(customer_name):
    customer = frappe.get_doc({
        "doctype": "Customer",
        "customer_name": customer_name,
        "customer_type": "Individual",
        "customer_group": "Shopify",
        "territory": "All Territories",

    })
    customer.insert(ignore_permissions=True)
    frappe.db.commit()
    return customer

def get_address(data, customer):
    if frappe.db.exists("Address", {'email_id': data.get('customer').get('email')}):
        customer_address = frappe.get_doc("Address", {'email_id': data.get('customer').get('email')})

    else:
        customer_address = frappe.get_doc({
            "doctype": "Address",
            "address_title": customer,
            "address_type": "Billing",
            "address_line1": data.get('customer').get("default_address").get("address1"),
            "address_line2": data.get('customer').get("default_address").get("address2"),
            "city": data.get('customer').get("default_address").get("city"),
            "state": data.get('customer').get("default_address").get("province"),
            "pincode": data.get('customer').get("default_address").get("zip"),
            "country": data.get('customer').get("default_address").get("country"),
            "email_id": data.get('customer').get("email"),
            "phone": data.get('customer').get("phone"),
        })
        #append the customer to address links
        
        customer_address.insert(ignore_permissions=True)
        frappe.db.commit()
    return customer_address.name
         


def get_tax(data):
	tax = []
	for item in data.get("line_items"):
		tax.append({
			"charge_type": "On Net Total",
			"account_head": "Output Tax IGST - DPL",
			"cost_center": "Main - DPL",
			"tax_amount": data.get("total_tax"),
            "description": "IGST - 5.00%"
		})
	return tax

def get_item(data):
    items = []
    for item in data.get("line_items"):
        item = {
            "item_code": item.get("sku"),
            "qty": item.get("quantity"),
            "rate": item.get("price"),
            "warehouse": "Finished Goods - DPL",
            "delivery_date": getdate(data.get("created_at")),
            "uom": "Meter",
            "gst_treatment": "Taxable",
            'igs_amount': get_igst(item)[0] if get_igst(item) else 0,
            'igs_rate': get_igst(item)[1] if get_igst(item) else 0,
            'sgst_amount': get_sgst(item)[0] if get_sgst(item) else 0,
            'sgst_rate': get_sgst(item)[1] if get_sgst(item) else 0,
            'cgst_amount': get_cgst(item)[0] if get_cgst(item) else 0,
            'cgst_rate': get_cgst(item)[1] if get_cgst(item) else 0,
            


        }
        items.append(item)
    return items

def create_sales_order(data):
    customer_name = data.get("customer").get("first_name") + " " + data.get("customer").get("last_name")
    if frappe.db.exists("Customer", {"customer_name": customer_name}):
        customer = frappe.get_doc("Customer", {"customer_name": customer_name})
    else:
        customer = create_customer(customer_name)

    items = get_item(data)
    taxes = get_tax(data)
    sales_order = frappe.get_doc({
        "doctype": "Sales Order",
        "shopify_order_id": data.get("id"),
        "shopify_order_number": data.get("name"),
        "customer": customer.name,
        "items": items,
        "delivery_date": getdate(data.get("created_at")),
        "order_type": "Sales",
        "company": "Doeraa Private Limited",
        "currency": data.get("currency"),
        "taxes_and_charges": "Output GST Out-state - DPL",
        "tax_category": "Ecommerce Integrations - Ignore",
        "taxes": taxes,
        "customer_address": get_address(data, customer_name),
		
    })

    sales_order.insert(ignore_permissions=True)
    frappe.db.commit()
    return sales_order.name

def get_igst(item):
    tax_lines = item.get("tax_lines")
    for tax_line in tax_lines:
        if tax_line.get("title") == "IGST":
            return float(tax_line.get("price")), float(tax_line.get("rate"))

def get_cgst(item):
    tax_lines = item.get("tax_lines")
    for tax_line in tax_lines:
        if tax_line.get("title") == "CGST":
            return float(tax_line.get("price")), float(tax_line.get("rate"))

def get_sgst(item):
	tax_lines = item.get("tax_lines")
	for tax_line in tax_lines:
		if tax_line.get("title") == "SGST":
			return float(tax_line.get("price")), float(tax_line.get("rate"))


@frappe.whitelist(allow_guest=True)
def delete_sales_orders():
    # orders = frappe.get_all("Sales Order", 'SAL-ORD-2024-05034')
    # for order in orders:
    #     sales_order = frappe.get_doc("Sales Order", order.name)
    frappe.delete_doc("Sales Order", 'SAL-ORD-2024-05034')
    frappe.db.commit()
    return "Sales Orders Deleted"

@frappe.whitelist(allow_guest=True)
def updtate_item_tax_template():
    # Execute a raw SQL query to find items with no HSN code and no entries in the taxes table
    items = frappe.db.sql("""
        SELECT name 
        FROM `tabItem` 
        WHERE gst_hsn_code IS NOT NULL 
        AND name NOT IN (
            SELECT parent 
            FROM `tabItem Tax` 
            WHERE parenttype = 'Item'
        )
    """, as_dict=True)

    for item in items:
        item_doc = frappe.get_doc("Item", item.get("name"))
        item_doc.append("taxes", {
            "item_tax_template": "GST 5% - DE",
            "tax_category": "In-State"
        })
        item_doc.append("taxes", {
            "item_tax_template": "GST 5% - DE",
            "tax_category": "Out-State"
        })
        item_doc.save()
        frappe.db.commit()

    return len(items)
