"""
Stripe Connector for Asirive Copartner — Phase 3 Integration
=============================================================
Handles B2B agency revenue operations:
  - Create and send client invoices
  - Create one-time payment links
  - Retrieve payment status
  - Log revenue to data/revenue.json for XPRIZE demo dashboard

This is how a solo founder + Copartner generates REAL revenue that
the XPRIZE judges can see on a live Stripe dashboard.

Setup:
    STRIPE_SECRET_KEY=sk_live_... in .env
    STRIPE_PUBLISHABLE_KEY=pk_live_... in .env
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("Copartner.Stripe")

try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False
    logger.warning("stripe not installed. Run: pip install stripe")

PROJECT_ROOT  = Path(__file__).parent.parent.parent
REVENUE_LOG   = PROJECT_ROOT / "data" / "revenue.json"


def _load_revenue_log() -> dict:
    if REVENUE_LOG.exists():
        try:
            return json.loads(REVENUE_LOG.read_text())
        except Exception:
            pass
    return {"invoices": [], "total_usd": 0.0}


def _save_revenue_log(data: dict):
    REVENUE_LOG.parent.mkdir(parents=True, exist_ok=True)
    REVENUE_LOG.write_text(json.dumps(data, indent=2))


class StripeConnector:
    """
    Manages Stripe operations for the Asirive B2B agency model.

    Usage:
        stripe_conn = StripeConnector(secret_key="sk_live_...")
        result = stripe_conn.create_invoice(
            client_email="client@company.com",
            client_name="Acme Corp",
            line_items=[
                {"description": "Landing page design & development", "amount_usd": 450.00},
                {"description": "Vercel deployment setup", "amount_usd": 50.00},
            ]
        )
        print(result["invoice_url"])  # Send this to client
    """

    def __init__(self, secret_key: Optional[str] = None):
        if not STRIPE_AVAILABLE:
            logger.error("stripe package required. Install: pip install stripe")
            self._ready = False
            return

        import os
        key = secret_key or os.environ.get("STRIPE_SECRET_KEY", "")
        if not key:
            logger.warning(
                "STRIPE_SECRET_KEY not set. Stripe in demo mode — "
                "calls will fail. Set the key in .env to enable live payments."
            )
            self._ready = False
        else:
            stripe.api_key = key
            self._ready = True
            logger.info("StripeConnector initialized")

    # ── Invoice creation ──────────────────────────────────────────────────────

    def create_invoice(
        self,
        client_email: str,
        client_name: str,
        line_items: list[dict],
        currency: str = "usd",
        days_until_due: int = 7,
        memo: str = "Asirive — Web Development Services",
        auto_send: bool = True,
    ) -> dict:
        """
        Create and optionally send a Stripe invoice to a client.

        Args:
            client_email:   Client's billing email.
            client_name:    Client's name / company name.
            line_items:     List of {description: str, amount_usd: float} dicts.
            currency:       ISO currency code (default: usd).
            days_until_due: Payment due in N days.
            memo:           Invoice memo / footer note.
            auto_send:      If True, email the invoice immediately.

        Returns:
            dict with: invoice_id, invoice_url, total_usd, status
        """
        if not self._ready:
            return self._demo_invoice(client_email, client_name, line_items)

        try:
            # Get or create customer
            customers = stripe.Customer.list(email=client_email, limit=1)
            if customers.data:
                customer = customers.data[0]
            else:
                customer = stripe.Customer.create(
                    email=client_email,
                    name=client_name,
                )

            # Create invoice
            invoice = stripe.Invoice.create(
                customer=customer.id,
                collection_method="send_invoice",
                days_until_due=days_until_due,
                footer=memo,
                currency=currency,
            )

            # Add line items
            total = 0.0
            for item in line_items:
                amount_cents = int(item["amount_usd"] * 100)
                stripe.InvoiceItem.create(
                    customer=customer.id,
                    invoice=invoice.id,
                    amount=amount_cents,
                    currency=currency,
                    description=item.get("description", "Service"),
                )
                total += item["amount_usd"]

            # Finalize and optionally send
            finalized = stripe.Invoice.finalize_invoice(invoice.id)
            if auto_send:
                stripe.Invoice.send_invoice(invoice.id)

            result = {
                "invoice_id":  invoice.id,
                "invoice_url": finalized.hosted_invoice_url or "",
                "invoice_pdf": finalized.invoice_pdf or "",
                "total_usd":   total,
                "status":      "sent" if auto_send else "finalized",
                "client":      client_name,
                "client_email": client_email,
            }

            self._log_revenue(result)
            logger.info(f"Invoice created: {invoice.id} | ${total:.2f} → {client_email}")
            return result

        except Exception as e:
            logger.error(f"Stripe invoice creation failed: {e}")
            return {"error": str(e)}

    def create_payment_link(
        self,
        name: str,
        amount_usd: float,
        currency: str = "usd",
        quantity: int = 1,
    ) -> dict:
        """
        Create a simple one-click Stripe Payment Link.
        Useful for quick service payments without a formal invoice.

        Returns:
            dict with: url, amount_usd
        """
        if not self._ready:
            return {"url": "[demo_payment_link]", "amount_usd": amount_usd}

        try:
            # Create a price object
            price = stripe.Price.create(
                unit_amount=int(amount_usd * 100),
                currency=currency,
                product_data={"name": name},
            )
            link = stripe.PaymentLink.create(
                line_items=[{"price": price.id, "quantity": quantity}]
            )
            logger.info(f"Payment link created: {link.url} | ${amount_usd:.2f}")
            return {"url": link.url, "amount_usd": amount_usd, "product": name}
        except Exception as e:
            logger.error(f"Payment link creation failed: {e}")
            return {"error": str(e)}

    def get_invoice_status(self, invoice_id: str) -> dict:
        """Check the status of an existing invoice."""
        if not self._ready:
            return {"status": "demo", "invoice_id": invoice_id}
        try:
            inv = stripe.Invoice.retrieve(invoice_id)
            return {
                "invoice_id": invoice_id,
                "status":     inv.status,
                "amount_due": inv.amount_due / 100,
                "paid":       inv.paid,
                "due_date":   inv.due_date,
            }
        except Exception as e:
            return {"error": str(e)}

    # ── Revenue logging ───────────────────────────────────────────────────────

    def _log_revenue(self, invoice_result: dict):
        """Append invoice to local revenue log (for XPRIZE demo dashboard)."""
        data = _load_revenue_log()
        data["invoices"].append({
            **invoice_result,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        data["total_usd"] = sum(
            inv.get("total_usd", 0) for inv in data["invoices"]
        )
        _save_revenue_log(data)

    def revenue_summary(self) -> dict:
        """Return revenue stats from the local log."""
        data = _load_revenue_log()
        return {
            "total_usd":    data.get("total_usd", 0.0),
            "invoice_count": len(data.get("invoices", [])),
            "invoices":     data.get("invoices", []),
        }

    # ── Demo mode ─────────────────────────────────────────────────────────────

    def _demo_invoice(self, email: str, name: str, items: list[dict]) -> dict:
        """Return a fake invoice result when Stripe key is not set."""
        total = sum(item.get("amount_usd", 0) for item in items)
        result = {
            "invoice_id":   "demo_inv_" + str(int(time.time())),
            "invoice_url":  "https://stripe.com/demo",
            "invoice_pdf":  "",
            "total_usd":    total,
            "status":       "demo",
            "client":       name,
            "client_email": email,
            "note":         "Set STRIPE_SECRET_KEY in .env to enable real payments",
        }
        self._log_revenue(result)
        return result
