import odoo_api
import config

uid, models = odoo_api.get_connection()
if uid:
    try:
        # Fetch one sale order
        ids = models.execute_kw(config.ODOO_DB, uid, config.ODOO_PASSWORD, 'sale.order', 'search', [[['state', 'in', ['sale', 'done']]]], {'limit': 1})
        if ids:
            so = models.execute_kw(config.ODOO_DB, uid, config.ODOO_PASSWORD, 'sale.order', 'read', [ids], {'fields': ['name', 'state', 'partner_id', 'client_order_ref', 'amount_tax', 'invoice_ids', 'date_order']})
            print("Sale Order:", so)
            
            # If invoices exist, fetch one
            if so[0].get('invoice_ids'):
                inv_id = so[0]['invoice_ids'][0]
                # Try account.invoice
                try:
                    inv = models.execute_kw(config.ODOO_DB, uid, config.ODOO_PASSWORD, 'account.invoice', 'read', [[inv_id]], {'fields': ['state', 'type']})
                    print("Invoice (account.invoice):", inv)
                except:
                    # Try account.move
                    inv = models.execute_kw(config.ODOO_DB, uid, config.ODOO_PASSWORD, 'account.move', 'read', [[inv_id]], {'fields': ['state', 'move_type']})
                    print("Invoice (account.move):", inv)
        else:
            print("No Sale Orders found.")
            
    except Exception as e:
        print(f"Error: {e}")
else:
    print("Connection failed")
