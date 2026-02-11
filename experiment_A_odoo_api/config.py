import os

# Odoo Connection Settings
ODOO_URL = os.getenv("ODOO_URL", "http://localhost:8069")
ODOO_DB = os.getenv("ODOO_DB", "Testbed_restore")
ODOO_USERNAME = os.getenv("ODOO_USERNAME", "admin")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "n!md4")

# Flask App Settings
DEBUG = True
SECRET_KEY = os.getenv("SECRET_KEY", "dev-key-change-in-prod")
