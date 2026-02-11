import xmlrpc.client
import datetime
import os
import config

# Configuration
ODOO_URL = config.ODOO_URL
ODOO_DB = config.ODOO_DB
ODOO_USERNAME = config.ODOO_USERNAME
ODOO_PASSWORD = config.ODOO_PASSWORD

def get_connection():
    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
        return uid, models
    except Exception as e:
        print(f"Odoo Connection Error: {e}")
        return None, None

def fetch_invoices(uid, models):
    # INCOMPLETE ORDERS Logic (Sale Orders + Verdict check)
    try:
        # Fetch relevant Sale Orders
        orders = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'sale.order', 'search_read',
            [[['state', 'in', ['draft', 'sent', 'cancel', 'sale', 'done']]]],
            {'fields': ['id', 'name', 'partner_id', 'date_order', 'state', 'amount_tax', 'client_order_ref', 'invoice_ids', 'amount_total'], 
             'limit': 100, 'order': 'date_order desc'}
        )
        
        # Collect all invoice IDs to fetch in bulk
        all_inv_ids = []
        for o in orders:
            if o.get('invoice_ids'):
                all_inv_ids.extend(o['invoice_ids'])
        
        inv_map = {}
        if all_inv_ids:
            all_inv_ids = list(set(all_inv_ids))
            # Try Account Invoice (Odoo 12) handling first
            try:
                inv_data = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'account.invoice', 'search_read',
                    [[['id', 'in', all_inv_ids]]],
                    {'fields': ['id', 'state', 'type']}
                )
                for inv in inv_data:
                    inv_map[inv['id']] = {'state': inv['state'], 'type': inv['type']}
            except:
                # Fallback to Account Move (Odoo 14+)
                try:
                    inv_data = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'account.move', 'search_read',
                        [[['id', 'in', all_inv_ids]]],
                        {'fields': ['id', 'state', 'move_type', 'payment_state']}
                    )
                    for inv in inv_data:
                        # Normalize state for logic
                        st = inv.get('payment_state', inv['state'])
                        if st == 'not_paid': st = 'open' 
                        inv_map[inv['id']] = {'state': st, 'type': inv['move_type']}
                except Exception as e:
                    print(f"Error fetching invoices details: {e}")

        incomplete_orders = []
        for o in orders:
            # "Verdict" Logic Refined
            # Default to "Invalid" (Incomplete) -> Show in dashboard
            verdict = "Invalid"
            
            # Map States
            # D/C = Draft/Cancel? Or Draft/Created? Usage suggests Draft/Sent => D/C.
            # SO = Sale Order (Confirmed/Done).
            # If state is cancel, we usually ignore
            if o['state'] == 'cancel':
                continue # Skip cancelled entirely
                
            q_state = 'D/C' if o['state'] in ['draft', 'sent'] else 'SO'
            
            # Taxable (Assumption: amount_tax > 0)
            is_taxable = o.get('amount_tax', 0) > 0
            taxable_str = 'Y' if is_taxable else 'N'
            
            # Reference
            ref_str = 'Y' if o.get('client_order_ref') else 'N'
            
            # Invoices
            o_inv_ids = o.get('invoice_ids', [])
            inv_count = len(o_inv_ids)
            inv_state = '-'
            paid_count = 0
            canceled_count = 0
            refund_draft = False
            for iid in o_inv_ids:
                inv = inv_map.get(iid)
                if not inv:
                    continue
                if inv.get('state') == 'paid':
                    paid_count += 1
                if inv.get('state') == 'cancel':
                    canceled_count += 1
                if inv.get('type') == 'out_refund' and inv.get('state') == 'draft':
                    refund_draft = True
            if inv_count == 1 and o_inv_ids[0] in inv_map:
                inv_state = inv_map[o_inv_ids[0]]['state']

            # Apply "Valid" (Hide) logic
            if q_state == 'D/C':
                # Draft/Confirmed with no invoice must be shown
                if inv_count == 0:
                    verdict = "Invalid"
                # Row 5: D/C, Tax N -> Ignore when invoices exist
                elif taxable_str == 'N':
                    verdict = "Valid"
                else:
                    # If at least one invoice is fully paid, consider it complete
                    if paid_count >= 1:
                        verdict = "Valid"

            if q_state == 'SO':
                if taxable_str == 'Y':
                    # Row 2: SO, Tax Y, Ref Y, Inv Count 1, Inv State paid -> Valid
                    if ref_str == 'Y' and inv_count == 1 and inv_state == 'paid':
                        verdict = "Valid"
                    # Taxable Multiple Invoices: valid if one paid and rest canceled
                    elif ref_str == 'Y' and inv_count > 1 and paid_count == 1 and canceled_count == inv_count - 1:
                        verdict = "Valid"
                else:
                    # Non-Taxable: no ref/invoice needed
                    if inv_count == 0:
                        verdict = "Valid"
                    else:
                        # Row 6: SO, Tax N -> Valid if Inv >= 1, out_invoice=paid, out_refund!=draft
                        if paid_count >= 1 and not refund_draft:
                            verdict = "Valid"

            # Determine Issue Label for UI
            issue_label = "Action Required" # Default

            if verdict == "Invalid":
                if q_state == 'D/C':
                    if inv_count == 0:
                        issue_label = "Not Invoiced"
                    elif taxable_str == 'Y' and ref_str == 'Y':
                        issue_label = "Draft with Reference"
                    else:
                        issue_label = "Open Invoice"
                elif q_state == 'SO':
                    if taxable_str == 'Y':
                        if ref_str == 'N':
                            issue_label = "No Ref"
                        elif inv_count > 1:
                            issue_label = "Multiple Invoices"
                        elif inv_count == 0:
                            issue_label = "Not Invoiced"
                        elif inv_state != 'draft':
                            issue_label = "Invoice Not Paid"
                    else:
                        # Non-Taxable Issues (should be rare with new rules)
                        if inv_count == 0:
                            issue_label = "Not Invoiced"
                        else:
                            issue_label = "Invoice Issue"

            # If Verdict is Invalid, it's an Incomplete Order -> Show it
            if verdict == "Invalid":
                incomplete_orders.append({
                    'id': o['id'],
                    'name': o['name'], 
                    'ref': o.get('client_order_ref', 'N/A'),
                    'partner_id': o['partner_id'],
                    'date_invoice': o['date_order'],
                    'amount_total': o['amount_total'],
                    'state': o['state'],
                    'issue': issue_label
                })
        
        return incomplete_orders
    except Exception as e:
        print(f"Fetch Incomplete Orders Error: {e}")
        return []

def fetch_journals(uid, models):
    # Unposted Journals (bank.deposit + account.move)
    try:
        bank_journal_names_raw = [
            'Awash Bank Kazanchis 01304108544700',
            'Oromia International Bank Sal.798577',
            'Oromia International Bank 2010301',
            'OBI GOFA 1100477900005',
            'Awash Bank 01320108544700',
            'Commercial Bank of Ethiopia 1000178884787',
            'Debub Global Bank',
            'Commercial Bank of Ethiopia 1000155628077',
            'Oromia International Bank 1070202/1',
            'Cooperative Bank Oromia 24634028',
            'Oromia International Bank 743829',
            'Wegagen Bank-07614268',
            'Nib International Bank 10468286',
            'United Bank 16350315018',
            'Cooperative Bank Oromia 1000081172947',
            'Oromia International Bank 2010308'
        ]
        bank_journal_names = set()
        for name in bank_journal_names_raw:
            bank_journal_names.add(name)
            bank_journal_names.add(f"{name} (ETB)")

        # Method 1: bank.deposit (draft/approved)
        deposits = []
        try:
            deposits = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'bank.deposit', 'search_read',
                [[['state', 'in', ['draft', 'approved']]]],
                {'fields': ['id', 'name', 'partner', 'date', 'amount', 'amount_total', 'state', 'journal_id'], 'limit': 50, 'order': 'date desc'}
            )
        except Exception as e:
            print(f"Bank deposit fetch error: {e}")

        # Method 2: account.move (draft/unposted, bank journals only)
        journal_ids = []
        try:
            journals = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'account.journal', 'search_read',
                [[['type', '=', 'bank'], ['name', 'in', list(bank_journal_names)]]],
                {'fields': ['id', 'name']}
            )
            journal_ids = [j['id'] for j in journals]
        except Exception as e:
            print(f"Bank journal lookup error: {e}")

        moves = []
        if journal_ids:
            try:
                moves = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'account.move', 'search_read',
                    [[['state', '=', 'draft'], ['journal_id', 'in', journal_ids]]],
                    {
                        'fields': ['id', 'partner', 'amount', 'date', 'state', 'journal_id', 'name', 'ref'],
                        'limit': 15500,
                        'order': 'date desc'
                    }
                )
                print(f"Found {len(moves)} account.move entries from these matched journals.")
            except Exception as e:
                print(f"Account move fetch error: {e}")

        # Fallback: fetch partner from account.move.line when missing
        partners_from_lines = {}
        if moves:
            missing_partner_ids = [m['id'] for m in moves if not m.get('partner')]
            if missing_partner_ids:
                try:
                    lines = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'account.move.line', 'search_read',
                        [[['move_id', 'in', missing_partner_ids], ['partner_id', '!=', False]]],
                        {'fields': ['move_id', 'partner_id'], 'limit': len(missing_partner_ids) * 5}
                    )
                    for line in lines:
                        m_id = line['move_id'][0]
                        if m_id not in partners_from_lines:
                            partners_from_lines[m_id] = line['partner_id']
                except Exception as e:
                    print(f"Error fetching partners from lines: {e}")

        # Normalize and merge
        merged = []
        for d in deposits:
            if d.get('journal_id') and d['journal_id'][1] not in bank_journal_names:
                continue
            partner_val = d.get('partner') or d.get('partner_id')
            merged.append({
                'id': d.get('id'),
                'name': d.get('name'),
                'partner': partner_val,
                'date': d.get('date'),
                'amount': d.get('amount_total', d.get('amount', 0)),
                'state': d.get('state', 'draft'),
                'journal_id': d.get('journal_id'),
                'source': 'deposit',
                'model': 'bank.deposit',
                'record_id': d.get('id')
            })

        for m in moves:
            partner_val = m.get('partner')
            ref_val = m.get('ref')

            is_unknown = False
            if not partner_val:
                is_unknown = True
            elif isinstance(partner_val, list) and 'unknown' in partner_val[1].lower():
                is_unknown = True

            if is_unknown:
                if m.get('id') in partners_from_lines:
                    partner_val = partners_from_lines[m['id']]
                elif ref_val and ref_val != m.get('name'):
                    partner_val = [0, ref_val]
                elif not partner_val:
                    partner_val = [0, 'Unknown']

            merged.append({
                'id': f"move_{m.get('id')}",
                'name': m.get('name'),
                'partner': partner_val,
                'date': m.get('date'),
                'amount': m.get('amount', 0),
                'state': m.get('state', 'draft'),
                'journal_id': m.get('journal_id'),
                'source': 'journal',
                'model': 'account.move',
                'record_id': m.get('id')
            })

        return merged
    except Exception as e:
        print(f"Fetch Unposted Journals Error: {e}")
        return []

def fetch_quotations(uid, models):
    # Quotations with Warehouse info
    try:
        return models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'sale.order', 'search_read',
           [[['state', 'in', ['draft', 'sent']]]],
           {'fields': ['id', 'name', 'partner_id', 'date_order', 'warehouse_id', 'amount_total'], 'limit': 11050, 'order': 'date_order desc'}
        )
    except: return []

def fetch_customers(uid, models):
    # New Customers with Order Counts
    try:
        # 1. Fetch recently created customers
        customers = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'search_read',
            [[['customer', '=', True]]],
            {'fields': ['id', 'name', 'create_date', 'partner_code', 'vat'], 'limit': 50, 'order': 'create_date desc'}
        )
        
        processed = []
        for c in customers:
            # 2. Count Quotations/Orders (Draft and Confirmed) for each customer
            # "status draft and confirm" -> draft, sent, sale, done
            count_domain = [['partner_id', '=', c['id']], ['state', 'in', ['draft', 'sent', 'sale', 'done']]]
            order_count = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'sale.order', 'search_count', [count_domain])

            # 3. Get latest activity date (optional, or just use create_date)
            # Staying fast, we'll use create_date or if needed fetch one order.
            # User wants "Number of Orders" displayed.
            
            partner_code = c.get('partner_code') or ''
            vat = c.get('vat') or ''
            if not partner_code or not vat:
                continue

            processed.append({
                'id': c['id'],
                'name': c['name'],
                'create_date': c['create_date'],
                'partner_code': partner_code,
                'order_count': order_count,
                # 'recent_quotation' can be removed if specific "Number of Orders" is preferred, 
                # but keeping a reference is good. Let's keep the count mainly.
            })
            
        return processed
    except Exception as e:
        print(f"Fetch Customers Error: {e}")
        return []

def fetch_overshoot(uid, models):
    # Overshoot with Delta and Total/Customer metrics
    try:
        orders = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'sale.order', 'search_read',
            [[['partner_id', '!=', False]]],
            {
                'fields': ['id', 'partner_id', 'amount_total', 'create_date'],
                'limit': 10000,
                'order': 'create_date desc'
            }
        )

        totals_by_partner = {}
        for o in orders:
            pid = o['partner_id'][0]
            if pid not in totals_by_partner:
                totals_by_partner[pid] = {
                    'partner_id': o['partner_id'],
                    'order_count': 0,
                    'orders_total': 0,
                    'latest_date': o.get('create_date')
                }
            totals_by_partner[pid]['order_count'] += 1
            totals_by_partner[pid]['orders_total'] += o.get('amount_total', 0) or 0
            if o.get('create_date'):
                totals_by_partner[pid]['latest_date'] = o['create_date']

        partner_ids = list(totals_by_partner.keys())
        partners = []
        if partner_ids:
            partners = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'search_read',
                [[['id', 'in', partner_ids]]],
                {'fields': ['id', 'name', 'credit_limit', 'current_balance']}
            )

        partner_map = {p['id']: p for p in partners}
        data = []
        for pid, agg in totals_by_partner.items():
            partner = partner_map.get(pid)
            if not partner:
                continue
            available = partner.get('current_balance', 0) or 0
            orders_total = agg['orders_total']
            delta = available - orders_total
            if delta >= 0:
                continue
            data.append({
                'id': pid,
                'partner_name': partner.get('name'),
                'order_count': agg['order_count'],
                'total_amount': orders_total,
                'customer_limit': available,
                'delta': delta,
                'latest_date': agg.get('latest_date')
            })
        return data
    except Exception as e:
        print(f"Fetch Overshoot Error: {e}")
        return []

def fetch_reconciliation(uid, models):
    try:
        reconciles = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'account.bank.statement.line', 'search_read',
            [[['is_reconciled', '=', False]]],
            {'fields': ['id', 'name', 'date', 'amount', 'partner_id'], 'limit': 15, 'order': 'date desc'}
        )
        return reconciles
    except: return []
