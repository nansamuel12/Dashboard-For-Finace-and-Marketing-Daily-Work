from flask import Flask, jsonify, render_template
import threading
import time
import odoo_api
import os
import config

app = Flask(__name__)
app.config.from_object(config)

# Global Data Cache
data_cache = {
    'invoices': [],
    'journals': [],
    'customers': [],
    'overshoot': [],
    'quotations': [],
    'reconciliation': [],
    'last_updated': None
}

CACHE_TTL_SECONDS = 5
cache_lock = threading.Lock()

def fetch_data_task():
    """Background task to fetch data from Odoo and update cache."""
    with cache_lock:
        print("Starting background data fetch...")
        uid, models = odoo_api.get_connection()
        if not uid:
            print("Failed to connect to Odoo.")
            return

        # Invoices
        try:
            data_cache['invoices'] = odoo_api.fetch_invoices(uid, models)
        except Exception as e:
            print(f"✗ Invoice fetch error: {e}")

        # Journals
        try:
            data_cache['journals'] = odoo_api.fetch_journals(uid, models)
        except Exception as e:
            print(f"✗ Journal fetch error: {e}")

        # Quotations
        try:
            data_cache['quotations'] = odoo_api.fetch_quotations(uid, models)
        except Exception as e:
            print(f"✗ Quotation fetch error: {e}")

        # Customers
        try:
            data_cache['customers'] = odoo_api.fetch_customers(uid, models)
        except Exception as e:
            print(f"✗ Customer fetch error: {e}")

        # Overshoot
        try:
            data_cache['overshoot'] = odoo_api.fetch_overshoot(uid, models)
        except Exception as e:
            print(f"✗ Overshoot fetch error: {e}")

        # Reconciliation
        try:
            data_cache['reconciliation'] = odoo_api.fetch_reconciliation(uid, models)
        except Exception as e:
            print(f"✗ Reconciliation fetch error: {e}")

        data_cache['last_updated'] = time.time()
        print(f"Data updated at {time.strftime('%H:%M:%S')}")


def ensure_fresh_data():
    if data_cache['last_updated'] is None:
        fetch_data_task()
        return
    age = time.time() - data_cache['last_updated']
    if age >= CACHE_TTL_SECONDS:
        fetch_data_task()

def start_scheduler():
    def scheduler_loop():
        fetch_data_task()
        while True:
            time.sleep(10)
            fetch_data_task()
    
    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()

# API Endpoints
@app.route('/')
def index():
    return render_template('index.html', odoo_url=app.config['ODOO_URL'])

@app.route('/api/invoices')
def get_invoices():
    ensure_fresh_data()
    return jsonify(data_cache['invoices'])

@app.route('/api/journals')
def get_journals():
    ensure_fresh_data()
    return jsonify(data_cache['journals'])

@app.route('/api/quotations/pending')
def get_quotations():
    ensure_fresh_data()
    return jsonify({'data': data_cache['quotations']})

@app.route('/api/customers')
def get_customers():
    ensure_fresh_data()
    return jsonify(data_cache['customers'])

@app.route('/api/overshoot')
def get_overshoot():
    ensure_fresh_data()
    return jsonify(data_cache['overshoot'])

@app.route('/api/reconciliation')
def get_reconciliation():
    ensure_fresh_data()
    return jsonify(data_cache['reconciliation'])

if __name__ == '__main__':
    start_scheduler()
    app.run(debug=True, port=5000)
