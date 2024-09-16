frappe.ui.form.on('Purchase Invoice', {
    refresh(frm) {
        if (!frm.doc.is_return && frm.doc.status != "Closed") {
            if (frm.doc.docstatus == 0) {
                frm.add_custom_button(
                    __("Purchase Receipt"),
                    function () {
                        if (!frm.doc.supplier) {
                            frappe.throw({
                                title: __("Mandatory"),
                                message: __("Please Select a Supplier"),
                            });
                        }

                        // Add debug log to ensure the button function is being called
                        console.log("Button clicked, initializing MultiSelectDialog...");

                        let dialog = new frappe.ui.form.MultiSelectDialog({
                            doctype: "Purchase Receipt",
                            target: frm,
                            setters: {
                                supplier: frm.doc.supplier,
                                posting_date: null
                            },
                            add_filters_group: 1,
                            date_field: "posting_date",
                            get_query() {
                                // Add debug log to ensure the get_query method is being called
                                console.log("Fetching query for MultiSelectDialog...");
                                return {
                                    filters: {
                                        docstatus: 1,
                                        status: ["not in", ["Closed", "On Hold"]],
                                        per_billed: ["<", 99.99],
                                        company: frm.doc.company,
                                    }
                                };
                            },
                            action(selections) {
                                // Add debug log to ensure the action method is being called
                                console.log("Action triggered with selections:", selections);
                                selections.forEach(pr => {
                                    frappe.call({
                                        method: "divyam.utils.get_purchase_receipt_items",
                                        args: {
                                            pr: pr
                                        },
                                        callback: function (r) {
                                            if (r.message) {
                                                console.log(r.message);
                                                frm.clear_table("items");
                                                r.message.forEach(d => {
                                                    frm.add_child("items", {
                                                        item_code: d.item_code,
                                                        item_name: d.item_name,
                                                        qty: d.qty,
                                                        rate: d.rate,
                                                        amount: d.amount,
                                                        uom: d.uom,
                                                        warehouse: d.warehouse,
                                                        purchase_receipt: pr
                                                        
                                                    });
                                                });
                                                frm.refresh_field("items");
                                                // Hide the dialog after processing selections
                                            }
                                        }
                                    });
                                });
                            }
                        });

                        // Add debug log to ensure the dialog is being shown
                        console.log("Showing MultiSelectDialog...");

                        // Set a timeout to automatically close the dialog after 5 seconds (5000 milliseconds)
                        setTimeout(function () {
                            console.log("Auto-closing MultiSelectDialog...");
                            dialog.dialog.hide();
                        }, 5000);
                    },
                    __("Fetch Items From")
                );
            }
        }
    }
});
