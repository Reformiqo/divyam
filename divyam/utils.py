#extend the subcontracting receipt.py dfile
import frappe
from frappe import _
from frappe import _, throw
from frappe.desk.notifications import clear_doctype_notifications
from frappe.model.mapper import get_mapped_doc
from frappe.query_builder.functions import CombineDatetime
from frappe.utils import cint, flt, get_datetime, getdate, nowdate
from pypika import functions as fn



@frappe.whitelist()
def get_invoice_total_report():
	# get the total amount of all the invoices which have place of supply 29-Karnataka, gst category Unregistered and grand total of les 250000


	invoices = frappe.get_all("Sales Invoice")
	total = 0
	for invoice in invoices:
		total += invoice.total
	return total


@frappe.whitelist()
def get_purchase_receipt_items(pr):
		doc = frappe.get_doc("Purchase Receipt", pr)
		items = doc.get('items')
		doc_items = []
		for item in items:
			# now add the item details like item code item name accepted qty and qty to the dict
			doc_items.append({
				"name": doc.name,
				'item_code': item.item_code,
				'item_name': item.item_name,
				'uom': item.uom,
				'rejected_qty': item.rejected_qty,
				'qty': item.qty,
				'rate': item.rate,
				'received_qty': item.received_qty,
				'price_list_rate': item.price_list_rate,
				'discount_amount': item.discount_amount,
				'amount': item.amount,
				'warehouse': item.warehouse,
				

			})
		
		return doc_items

@frappe.whitelist()
def make_purchase_invoice(source_name, target_doc=None, args=None):
	bill = frappe.db.get_single_value("Buying Settings", "bill_for_rejected_quantity_in_purchase_invoice")
	if bill:
		frappe.db.set_value("Buying Settings", "Buying Settings", "bill_for_rejected_quantity_in_purchase_invoice", 0)
	from erpnext.accounts.party import get_payment_terms_template

	doc = frappe.get_doc("Purchase Receipt", source_name)
	returned_qty_map = get_returned_qty_map(source_name)
	invoiced_qty_map = get_invoiced_qty_map(source_name)

	def set_missing_values(source, target):
		if len(target.get("items")) == 0:
			frappe.throw(_("All items have already been Invoiced/Returned"))

		doc = frappe.get_doc(target)
		doc.payment_terms_template = get_payment_terms_template(source.supplier, "Supplier", source.company)
		doc.run_method("onload")
		doc.run_method("set_missing_values")

		if args and args.get("merge_taxes"):
			merge_taxes(source.get("taxes") or [], doc)

		doc.run_method("calculate_taxes_and_totals")
		doc.set_payment_schedule()

	def update_item(source_doc, target_doc, source_parent):
		target_doc.qty, returned_qty = get_pending_qty(source_doc)
		if frappe.db.get_single_value("Buying Settings", "bill_for_rejected_quantity_in_purchase_invoice"):
			target_doc.rejected_qty = 0
		target_doc.stock_qty = flt(target_doc.qty) * flt(
			target_doc.conversion_factor, target_doc.precision("conversion_factor")
		)
		returned_qty_map[source_doc.name] = returned_qty

	def get_pending_qty(item_row):
		qty = item_row.qty
		if frappe.db.get_single_value("Buying Settings", "bill_for_rejected_quantity_in_purchase_invoice"):
			qty = item_row.received_qty
		pending_qty = qty - invoiced_qty_map.get(item_row.name, 0)
		returned_qty = flt(returned_qty_map.get(item_row.name, 0))
		if returned_qty:
			if returned_qty >= pending_qty:
				pending_qty = 0
				returned_qty -= pending_qty
			else:
				pending_qty -= returned_qty
				returned_qty = 0
		return pending_qty, returned_qty

	doclist = get_mapped_doc(
		"Purchase Receipt",
		source_name,
		{
			"Purchase Receipt": {
				"doctype": "Purchase Invoice",
				"field_map": {
					"supplier_warehouse": "supplier_warehouse",
					"is_return": "is_return",
					"bill_date": "bill_date",
				},
				"validation": {
					"docstatus": ["=", 1],
				},
			},
			"Purchase Receipt Item": {
				"doctype": "Purchase Invoice Item",
				"field_map": {
					"name": "pr_detail",
					"parent": "purchase_receipt",
					"qty": "qty",
					"purchase_order_item": "po_detail",
					"purchase_order": "purchase_order",
					"is_fixed_asset": "is_fixed_asset",
					"asset_location": "asset_location",
					"asset_category": "asset_category",
					"wip_composite_asset": "wip_composite_asset",
				},
				"postprocess": update_item,
				"filter": lambda d: get_pending_qty(d)[0] <= 0
				if not doc.get("is_return")
				else get_pending_qty(d)[0] > 0,
			},
			"Purchase Taxes and Charges": {
				"doctype": "Purchase Taxes and Charges",
				"add_if_empty": True,
				"ignore": args.get("merge_taxes") if args else 0,
			},
		},
		target_doc,
		set_missing_values,
	)

	return doclist


def get_invoiced_qty_map(purchase_receipt):
	"""returns a map: {pr_detail: invoiced_qty}"""
	invoiced_qty_map = {}

	for pr_detail, qty in frappe.db.sql(
		"""select pr_detail, qty from `tabPurchase Invoice Item`
		where purchase_receipt=%s and docstatus=1""",
		purchase_receipt,
	):
		if not invoiced_qty_map.get(pr_detail):
			invoiced_qty_map[pr_detail] = 0
		invoiced_qty_map[pr_detail] += qty

	return invoiced_qty_map


def get_returned_qty_map(purchase_receipt):
	"""returns a map: {so_detail: returned_qty}"""
	returned_qty_map = frappe._dict(
		frappe.db.sql(
			"""select pr_item.purchase_receipt_item, abs(pr_item.qty) as qty
		from `tabPurchase Receipt Item` pr_item, `tabPurchase Receipt` pr
		where pr.name = pr_item.parent
			and pr.docstatus = 1
			and pr.is_return = 1
			and pr.return_against = %s
	""",
			purchase_receipt,
		)
	)

	return returned_qty_map
