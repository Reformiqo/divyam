app_name = "divyam"
app_title = "Divyam"
app_publisher = "erpera"
app_description = "Divyam"
app_email = "info@erpera.io"
app_license = "mit"
# required_apps = []

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/divyam/css/divyam.css"
# app_include_js = "/assets/divyam/js/divyam.js"

# include js, css files in header of web template
# web_include_css = "/assets/divyam/css/divyam.css"
# web_include_js = "/assets/divyam/js/divyam.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "divyam/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "divyam/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "divyam.utils.jinja_methods",
# 	"filters": "divyam.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "divyam.install.before_install"
# after_install = "divyam.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "divyam.uninstall.before_uninstall"
# after_uninstall = "divyam.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "divyam.utils.before_app_install"
# after_app_install = "divyam.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "divyam.utils.before_app_uninstall"
# after_app_uninstall = "divyam.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "divyam.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

override_doctype_class = {
	"Subcontracting Receipt": "divyam.subcontracting.SubcontractingReceipt",
}

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

scheduler_events = {
# 	"all": [
# 		"divyam.tasks.all"
# 	],
# 	"daily": [
# 		"divyam.tasks.daily"
# 	],
# 	"hourly": [
# 		"divyam.tasks.hourly"
# 	],
# 	"weekly": [
# 		"divyam.tasks.weekly"
# 	],
# 	"monthly": [
# 		"divyam.tasks.monthly"
# 	],  
#set cron job for every 5 minutes
    "cron": {
        "*/5 * * * *": [
            "divyam.shopify.get_shopify_data",
        ]
    }
}

# Testing
# -------

# before_tests = "divyam.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "divyam.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "divyam.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["divyam.utils.before_request"]
# after_request = ["divyam.utils.after_request"]

# Job Events
# ----------
# before_job = ["divyam.utils.before_job"]
# after_job = ["divyam.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"divyam.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

fixtures = [
    {"doctype": "Client Script", 
    "filters": [["module" , "in" , ("Divyam" )]]
    },
    {"doctype": "Custom Field",
    "filters": [["module" , "in" , ("Divyam" )]]
    },
  
    ]