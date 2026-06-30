from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import escape
import hmac
import json
from typing import Any
from urllib.parse import parse_qs, urlparse

from .config import settings
from .models import LowBalanceAlert, PaymentConfirmation, SubscriptionRequest, ValidationError
from .security import verify_signature
from .services import SeegProtectService
from .sms import SmsGateway
from .storage import Storage


storage = Storage(settings.database_path)
service = SeegProtectService(settings, storage, SmsGateway(settings))


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "SEEGProtectHTTP/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/health":
            self.send_json(
                200,
                {
                    "status": "ok",
                    "service": settings.app_name,
                    "version": settings.version,
                },
            )
            return

        if parsed.path == "/events":
            if not self.require_admin(query):
                return
            self.send_json(200, {"events": storage.recent_events(limit=self.query_limit(query, 20))})
            return

        if parsed.path == "/subscriptions":
            if not self.require_admin(query):
                return
            self.send_json(200, {"subscriptions": storage.list_subscriptions(self.query_limit(query, 50))})
            return

        if parsed.path == "/payments":
            if not self.require_admin(query):
                return
            self.send_json(200, {"payments": storage.list_payments(self.query_limit(query, 50))})
            return

        if parsed.path == "/notifications":
            if not self.require_admin(query):
                return
            self.send_json(200, {"notifications": storage.list_notifications(self.query_limit(query, 50))})
            return

        if parsed.path == "/meters":
            if not self.require_admin(query):
                return
            meter_id = self.query_value(query, "meter_id")
            if not meter_id:
                self.send_json(422, {"error": "validation_error", "message": "meter_id is required"})
                return
            detail = storage.meter_detail(meter_id, self.query_limit(query, 20))
            if not detail:
                self.send_json(404, {"error": "meter_not_found", "meter_id": meter_id})
                return
            self.send_json(200, {"meter": detail})
            return

        if parsed.path == "/meter":
            if not self.require_admin(query, html=True):
                return
            meter_id = self.query_value(query, "meter_id")
            self.send_html(200, self.meter_html(meter_id))
            return

        if parsed.path == "/architecture":
            if not self.require_admin(query, html=True):
                return
            self.send_html(200, self.architecture_html())
            return

        if parsed.path == "/roadmap":
            if not self.require_admin(query, html=True):
                return
            self.send_html(200, self.roadmap_html())
            return

        if parsed.path == "/dashboard":
            if not self.require_admin(query, html=True):
                return
            self.send_html(200, self.dashboard_html())
            return

        if parsed.path == "/dashboards":
            if not self.require_admin(query, html=True):
                return
            self.send_html(200, self.dashboards_html())
            return

        if parsed.path == "/":
            self.send_json(
                200,
                {
                    "service": settings.app_name,
                    "endpoints": [
                        "GET /health",
                        "GET /events?limit=20",
                        "GET /subscriptions?limit=50",
                        "GET /payments?limit=50",
                        "GET /notifications?limit=50",
                        "GET /meters?meter_id=...",
                        "GET /meter?meter_id=...",
                        "GET /dashboards",
                        "GET /dashboard",
                        "GET /architecture",
                        "GET /roadmap",
                        "POST /webhooks/subscriptions",
                        "POST /webhooks/payments",
                        "POST /webhooks/low-balance",
                    ],
                },
            )
            return

        self.send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        raw_body = self.read_body()
        if not verify_signature(settings.webhook_secret, raw_body, self.headers.get("X-SEEG-Signature")):
            self.send_json(401, {"error": "invalid_signature"})
            return

        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
            if not isinstance(payload, dict):
                raise ValidationError("JSON body must be an object.")

            parsed = urlparse(self.path)
            if parsed.path == "/webhooks/subscriptions":
                response = service.register_subscription(SubscriptionRequest.from_payload(payload))
                self.send_json(202, response)
                return

            if parsed.path == "/webhooks/payments":
                response = service.confirm_payment(PaymentConfirmation.from_payload(payload))
                self.send_json(202, response)
                return

            if parsed.path == "/webhooks/low-balance":
                response = service.handle_low_balance(LowBalanceAlert.from_payload(payload))
                self.send_json(202, response)
                return

            self.send_json(404, {"error": "not_found"})
        except json.JSONDecodeError:
            self.send_json(400, {"error": "invalid_json"})
        except ValidationError as exc:
            self.send_json(422, {"error": "validation_error", "message": str(exc)})

    def read_body(self) -> bytes:
        content_length = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(content_length)

    def send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, status_code: int, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def query_limit(query: dict[str, list[str]], default: int) -> int:
        try:
            value = int(query.get("limit", [str(default)])[0])
        except ValueError:
            value = default
        return max(1, min(value, 100))

    @staticmethod
    def query_value(query: dict[str, list[str]], name: str) -> str:
        return (query.get(name, [""])[0] or "").strip()

    def require_admin(self, query: dict[str, list[str]], html: bool = False) -> bool:
        if not settings.admin_token:
            return True

        token = self.headers.get("X-Admin-Token") or self.query_value(query, "token")
        if hmac.compare_digest(token, settings.admin_token):
            return True

        if html:
            self.send_html(401, self.login_html())
        else:
            self.send_json(401, {"error": "admin_auth_required"})
        return False

    @staticmethod
    def auth_query() -> str:
        return f"?token={settings.admin_token}" if settings.admin_token else ""

    def admin_link(self, path: str) -> str:
        if not settings.admin_token:
            return path
        separator = "&" if "?" in path else "?"
        return f"{path}{separator}token={settings.admin_token}"

    def login_html(self) -> str:
        return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(settings.app_name)} - Acces admin</title>
  <style>
    body {{ font-family:"Segoe UI", Arial, sans-serif; margin:0; background:#f4f7f8; color:#142126; display:grid; min-height:100vh; place-items:center; }}
    .panel {{ width:min(460px, calc(100vw - 32px)); background:white; border:1px solid #d8e1e4; border-radius:8px; padding:22px; box-shadow:0 10px 28px rgba(20,33,38,.08); }}
    h1 {{ margin:0 0 8px; font-size:24px; }}
    p {{ color:#68767d; }}
    form {{ display:flex; gap:8px; margin-top:16px; }}
    input {{ flex:1; padding:10px; border:1px solid #b7c5c9; border-radius:6px; }}
    button {{ padding:10px 14px; border:0; border-radius:6px; background:#0b6b4f; color:white; font-weight:650; }}
  </style>
</head>
<body>
  <section class="panel">
    <h1>Acces admin</h1>
    <p>Entre le token admin pour consulter les donnees SEEG Protect.</p>
    <form method="get">
      <input name="token" type="password" placeholder="Token admin" required>
      <button type="submit">Entrer</button>
    </form>
  </section>
</body>
</html>"""

    def dashboard_html(self) -> str:
        summary = storage.dashboard_summary()
        metrics = storage.dashboard_metrics()
        subscriptions = storage.list_subscriptions(10)
        notifications = storage.list_notifications(10)
        events = storage.recent_events(10)
        return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(settings.app_name)} - Tableau de bord</title>
  <style>
    :root {{ --ink:#142126; --muted:#68767d; --line:#d8e1e4; --soft:#f4f7f8; --panel:#ffffff; --brand:#0b6b4f; --brand2:#15936b; --warn:#c47a00; --bad:#b23b3b; }}
    * {{ box-sizing: border-box; }}
    body {{ font-family: "Segoe UI", Arial, sans-serif; margin: 0; color: var(--ink); background: var(--soft); }}
    header {{ background: linear-gradient(135deg, #0b6b4f, #173f49); color: white; padding: 22px 28px; }}
    main {{ padding: 22px 28px 34px; max-width: 1240px; margin: 0 auto; }}
    h1 {{ font-size: 28px; margin: 0 0 6px; letter-spacing: 0; }}
    h2 {{ font-size: 18px; margin: 0 0 12px; }}
    p {{ color: var(--muted); }}
    nav {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:16px; }}
    nav a, .button {{ color:white; background:rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.25); padding:8px 11px; border-radius:6px; text-decoration:none; font-size:14px; }}
    .grid {{ display:grid; grid-template-columns: repeat(12, 1fr); gap:16px; }}
    .stats {{ margin: 20px 0; }}
    .stat, .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; box-shadow: 0 8px 20px rgba(20,33,38,.04); }}
    .span-3 {{ grid-column: span 3; }}
    .span-4 {{ grid-column: span 4; }}
    .span-6 {{ grid-column: span 6; }}
    .span-12 {{ grid-column: span 12; }}
    .label {{ color: var(--muted); font-size: 13px; }}
    .value {{ font-size: 30px; font-weight: 750; margin-top: 6px; }}
    .subtle {{ color: var(--muted); font-size:13px; margin-top:8px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid var(--line); border-radius: 8px; overflow:hidden; }}
    th, td {{ text-align: left; border-bottom: 1px solid #e8eef0; padding: 10px; font-size: 13px; vertical-align: top; }}
    th {{ background: #eef5f3; color: #263238; font-weight: 650; }}
    tr:last-child td {{ border-bottom: 0; }}
    a {{ color: var(--brand); }}
    form {{ display: flex; gap: 8px; margin: 0; flex-wrap: wrap; }}
    input {{ padding: 10px; border: 1px solid #b7c5c9; border-radius: 6px; min-width: 280px; }}
    button {{ padding: 10px 14px; border: 0; border-radius: 6px; background: var(--brand); color: white; cursor: pointer; font-weight:650; }}
    .bar-row {{ display:grid; grid-template-columns: 150px 1fr 44px; gap: 10px; align-items:center; margin: 10px 0; }}
    .bar-track {{ height: 12px; background:#e7edef; border-radius:999px; overflow:hidden; }}
    .bar-fill {{ height:100%; background: linear-gradient(90deg, var(--brand2), var(--brand)); border-radius:999px; }}
    .timeline {{ display:flex; gap:8px; align-items:end; height:150px; padding-top:10px; }}
    .day {{ flex:1; display:flex; flex-direction:column; align-items:center; gap:8px; }}
    .day-bar {{ width:100%; max-width:42px; min-height:3px; background:linear-gradient(180deg, #24a47a, #0b6b4f); border-radius:6px 6px 0 0; }}
    .day-label {{ font-size:11px; color:var(--muted); }}
    .status-pill {{ display:inline-block; padding:4px 8px; border-radius:999px; background:#e9f5ef; color:#0b6b4f; font-weight:650; }}
    @media (max-width: 850px) {{ .span-3, .span-4, .span-6 {{ grid-column: span 12; }} main {{ padding:16px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(settings.app_name)}</h1>
    <div>Supervision des abonnements, paiements, alertes et notifications SMS.</div>
    <nav>
      <a href="{self.admin_link("/dashboard")}">Tableau de bord</a>
      <a href="{self.admin_link("/architecture")}">Architecture</a>
      <a href="{self.admin_link("/roadmap")}">Suivi projet</a>
      <a href="{self.admin_link("/subscriptions?limit=20")}">Souscriptions JSON</a>
      <a href="{self.admin_link("/notifications?limit=20")}">Notifications JSON</a>
    </nav>
  </header>
  <main>
    <section class="grid stats">
      {self.stat_html("Souscriptions", summary["subscriptions"])}
      {self.stat_html("Actives", summary["active_subscriptions"])}
      {self.stat_html("Paiements", summary["payments"])}
      {self.stat_html("SMS/notifications", summary["notifications"])}
    </section>
    <section class="grid">
      <div class="panel span-6">
        <h2>Recherche compteur</h2>
        <form action="/meter" method="get">
          {self.hidden_token_input()}
          <input name="meter_id" placeholder="Exemple : api-meter-1782848694" required>
          <button type="submit">Ouvrir la fiche</button>
        </form>
        <div class="subtle">La fiche compteur regroupe abonnement, paiement, SMS et evenements techniques.</div>
      </div>
      <div class="panel span-6">
        <h2>Statut des abonnements</h2>
        {self.bar_chart_html(metrics["subscription_statuses"], "status")}
      </div>
      <div class="panel span-6">
        <h2>SMS par jour</h2>
        {self.timeline_html(metrics["notification_days"])}
      </div>
      <div class="panel span-6">
        <h2>Statut des SMS</h2>
        {self.donut_chart_html(metrics["notification_statuses"])}
      </div>
      <div class="panel span-6">
        <h2>Evenements techniques</h2>
        {self.bar_chart_html(metrics["event_types"], "event_type")}
      </div>
      <div class="panel span-6">
        <h2>Avancement mise en ligne</h2>
        {self.progress_html("MVP fonctionnel", 100)}
        {self.progress_html("Dashboard partenaire", 85)}
        {self.progress_html("Securite admin", 75)}
        {self.progress_html("SMS reel fournisseur", 35)}
        <div class="subtle">Voir le detail dans la page Suivi projet.</div>
      </div>
      <div class="panel span-12">
        <h2>Dernieres souscriptions</h2>
        {self.table_html(subscriptions, ["subscription_id", "meter_id", "phone_number", "status", "created_at"])}
      </div>
      <div class="panel span-12">
        <h2>Derniers SMS</h2>
        {self.table_html(notifications, ["meter_id", "phone_number", "status", "message", "created_at"])}
      </div>
      <div class="panel span-12">
        <h2>Journal technique recent</h2>
        {self.table_html(events, ["event_type", "reference", "created_at"])}
      </div>
    </section>
  </main>
</body>
</html>"""

    def meter_html(self, meter_id: str) -> str:
        if not meter_id:
            content = "<p>Renseigne un identifiant compteur depuis le tableau de bord.</p>"
        else:
            detail = storage.meter_detail(meter_id, 50)
            if not detail:
                content = f"<p>Compteur introuvable : <strong>{escape(meter_id)}</strong></p>"
            else:
                subscription = detail["subscription"]
                content = f"""
    <section class="stats">
      {self.stat_html("Statut", str(subscription["status"]))}
      {self.stat_html("Paiements", len(detail["payments"]))}
      {self.stat_html("SMS", len(detail["notifications"]))}
      {self.stat_html("Evenements", len(detail["events"]))}
    </section>
    <h2>Abonnement</h2>
    {self.table_html([subscription], ["subscription_id", "meter_id", "phone_number", "customer_ref", "status", "created_at", "activated_at"])}
    <h2>Paiements</h2>
    {self.table_html(detail["payments"], ["transaction_id", "amount_xaf", "status", "paid_at", "created_at"])}
    <h2>SMS et notifications</h2>
    {self.table_html(detail["notifications"], ["phone_number", "channel", "status", "message", "created_at"])}
    <h2>Evenements compteur</h2>
    {self.table_html(detail["events"], ["event_type", "reference", "created_at"])}
"""

        return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(settings.app_name)} Compteur</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; color: #172026; background: #f5f7f8; }}
    header {{ background: #0b6b4f; color: white; padding: 18px 24px; }}
    main {{ padding: 20px 24px; max-width: 1180px; margin: 0 auto; }}
    h1 {{ font-size: 24px; margin: 0; }}
    h2 {{ font-size: 18px; margin: 24px 0 10px; }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }}
    .stat {{ background: white; border: 1px solid #dbe3e5; border-radius: 6px; padding: 14px; }}
    .label {{ color: #5d6b72; font-size: 13px; }}
    .value {{ font-size: 24px; font-weight: 700; margin-top: 6px; overflow-wrap: anywhere; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dbe3e5; }}
    th, td {{ text-align: left; border-bottom: 1px solid #e7ecee; padding: 9px; font-size: 13px; vertical-align: top; }}
    th {{ background: #eef3f1; color: #263238; }}
    a {{ color: #0b6b4f; }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(settings.app_name)} - Compteur {escape(meter_id or "")}</h1>
  </header>
  <main>
    <p><a href="{self.admin_link("/dashboard")}">Retour au tableau de bord</a></p>
    {content}
  </main>
</body>
</html>"""

    def dashboards_html(self) -> str:
        summary = storage.dashboard_summary()
        return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(settings.app_name)} - Portail partenaires</title>
  <style>
    :root {{ --ink:#142126; --muted:#68767d; --line:#d8e1e4; --soft:#f4f7f8; --panel:#fff; --brand:#0b6b4f; --brand2:#173f49; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--soft); color:var(--ink); font-family:"Segoe UI", Arial, sans-serif; }}
    header {{ background:linear-gradient(135deg, #0b6b4f, #173f49); color:white; padding:30px; }}
    main {{ max-width:1180px; margin:0 auto; padding:24px 30px 40px; }}
    h1 {{ margin:0 0 8px; font-size:32px; letter-spacing:0; }}
    h2 {{ margin:0 0 10px; font-size:18px; }}
    p {{ color:var(--muted); }}
    .lead {{ color:rgba(255,255,255,.84); max-width:760px; }}
    .grid {{ display:grid; grid-template-columns:repeat(12, 1fr); gap:16px; }}
    .card {{ grid-column:span 6; background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:18px; box-shadow:0 8px 20px rgba(20,33,38,.05); }}
    .kpi {{ grid-column:span 3; background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; }}
    .value {{ font-size:30px; font-weight:800; color:var(--brand); margin-top:6px; }}
    .button {{ display:inline-block; margin-top:10px; padding:10px 13px; border-radius:6px; background:var(--brand); color:white; text-decoration:none; font-weight:700; }}
    .secondary {{ background:#eef5f3; color:var(--brand); }}
    .label {{ color:var(--muted); font-size:13px; }}
    .toplinks {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:18px; }}
    .toplinks a {{ color:white; background:rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.25); padding:8px 11px; border-radius:6px; text-decoration:none; font-size:14px; }}
    @media (max-width:850px) {{ .card,.kpi {{ grid-column:span 12; }} main {{ padding:16px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Portail partenaires</h1>
    <div class="lead">Acces centralise aux tableaux de bord, au suivi projet, a l'architecture et aux fiches compteurs SEEG Protect.</div>
    <div class="toplinks">
      <a href="{self.admin_link('/dashboard')}">Dashboard operationnel</a>
      <a href="{self.admin_link('/roadmap')}">Suivi projet</a>
      <a href="{self.admin_link('/architecture')}">Architecture</a>
    </div>
  </header>
  <main>
    <section class="grid">
      <div class="kpi"><div class="label">Souscriptions</div><div class="value">{summary["subscriptions"]}</div></div>
      <div class="kpi"><div class="label">Actives</div><div class="value">{summary["active_subscriptions"]}</div></div>
      <div class="kpi"><div class="label">Paiements</div><div class="value">{summary["payments"]}</div></div>
      <div class="kpi"><div class="label">SMS</div><div class="value">{summary["notifications"]}</div></div>

      <article class="card">
        <h2>Dashboard operationnel</h2>
        <p>KPIs, graphiques, SMS par jour, statuts, souscriptions recentes et journal technique.</p>
        <a class="button" href="{self.admin_link('/dashboard')}">Ouvrir</a>
      </article>
      <article class="card">
        <h2>Suivi projet partenaire</h2>
        <p>Avancement, lots de mise en ligne, decisions restantes et preuve de demonstration.</p>
        <a class="button" href="{self.admin_link('/roadmap')}">Ouvrir</a>
      </article>
      <article class="card">
        <h2>Architecture fonctionnelle</h2>
        <p>Scenario metier, schema technique et explication des flux HTTP, stockage et SMS.</p>
        <a class="button" href="{self.admin_link('/architecture')}">Ouvrir</a>
      </article>
      <article class="card">
        <h2>Fiche compteur</h2>
        <p>Recherche detaillee d'un compteur : abonnement, paiement, SMS et historique technique.</p>
        <a class="button secondary" href="{self.admin_link('/dashboard')}">Rechercher depuis le dashboard</a>
      </article>
    </section>
  </main>
</body>
</html>"""

    def roadmap_html(self) -> str:
        return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(settings.app_name)} - Suivi projet</title>
  <style>
    :root {{ --ink:#142126; --muted:#68767d; --line:#d8e1e4; --soft:#f4f7f8; --panel:#fff; --brand:#0b6b4f; --amber:#c47a00; --blue:#256f9c; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--soft); color:var(--ink); font-family:"Segoe UI", Arial, sans-serif; }}
    header {{ background:linear-gradient(135deg, #173f49, #0b6b4f); color:white; padding:24px 30px; }}
    main {{ max-width:1220px; margin:0 auto; padding:24px 30px 38px; }}
    h1 {{ margin:0 0 6px; font-size:30px; letter-spacing:0; }}
    h2 {{ margin:0 0 12px; font-size:18px; }}
    h3 {{ margin:0 0 8px; font-size:15px; color:#173f49; }}
    p {{ color:var(--muted); }}
    a {{ color:var(--brand); }}
    nav {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:16px; }}
    nav a {{ color:white; background:rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.25); padding:8px 11px; border-radius:6px; text-decoration:none; font-size:14px; }}
    .grid {{ display:grid; grid-template-columns:repeat(12, 1fr); gap:16px; }}
    .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:17px; box-shadow:0 8px 20px rgba(20,33,38,.04); }}
    .span-3 {{ grid-column:span 3; }}
    .span-4 {{ grid-column:span 4; }}
    .span-6 {{ grid-column:span 6; }}
    .span-12 {{ grid-column:span 12; }}
    .kpi {{ font-size:28px; font-weight:800; color:var(--brand); margin-top:5px; }}
    .tag {{ display:inline-block; padding:4px 8px; border-radius:999px; background:#e9f5ef; color:#0b6b4f; font-weight:700; font-size:12px; }}
    .timeline {{ position:relative; margin-top:8px; }}
    .item {{ display:grid; grid-template-columns:110px 1fr; gap:14px; padding:12px 0; border-bottom:1px solid #e7edef; }}
    .item:last-child {{ border-bottom:0; }}
    .date {{ font-weight:750; color:var(--brand); }}
    .bar {{ height:10px; background:#e7edef; border-radius:999px; overflow:hidden; margin:8px 0 3px; }}
    .fill {{ height:100%; background:linear-gradient(90deg, #24a47a, #0b6b4f); }}
    table {{ width:100%; border-collapse:collapse; }}
    th, td {{ text-align:left; border-bottom:1px solid #e7edef; padding:10px; font-size:13px; vertical-align:top; }}
    th {{ background:#eef5f3; color:#173f49; }}
    @media (max-width:850px) {{ .span-3,.span-4,.span-6 {{ grid-column:span 12; }} main {{ padding:16px; }} .item {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Suivi projet partenaire</h1>
    <div>Etat d'avancement, modules disponibles, prochaines decisions et criteres de demonstration.</div>
    <nav>
      <a href="{self.admin_link("/dashboard")}">Tableau de bord</a>
      <a href="{self.admin_link("/architecture")}">Architecture</a>
      <a href="{self.admin_link("/roadmap")}">Suivi projet</a>
    </nav>
  </header>
  <main>
    <section class="grid">
      <div class="panel span-3"><h2>Statut</h2><span class="tag">Demo pre-prod</span><div class="kpi">V0.1</div></div>
      <div class="panel span-3"><h2>Modules</h2><div class="kpi">7</div><p>API, dashboard, SMS, securite, architecture, fiche compteur, demo.</p></div>
      <div class="panel span-3"><h2>Tests</h2><div class="kpi">7 OK</div><p>Suite automatique et scenario API valides.</p></div>
      <div class="panel span-3"><h2>Priorite</h2><div class="kpi">SMS reel</div><p>Choix fournisseur et credentials.</p></div>

      <div class="panel span-6">
        <h2>Avancement par chantier</h2>
        {self.progress_html("Moteur PROTEC MVP", 100)}
        {self.progress_html("Dashboard partenaire", 90)}
        {self.progress_html("Architecture lisible DAF/DSI", 90)}
        {self.progress_html("Securite admin optionnelle", 75)}
        {self.progress_html("Mise en ligne pilote", 50)}
        {self.progress_html("SMS fournisseur reel", 35)}
      </div>
      <div class="panel span-6">
        <h2>Scenario de demonstration</h2>
        <div class="timeline">
          <div class="item"><div class="date">Etape 1</div><div><strong>Souscription</strong><p>La SEEG envoie une demande de protection compteur via webhook.</p></div></div>
          <div class="item"><div class="date">Etape 2</div><div><strong>Paiement</strong><p>Le paiement active l'abonnement et rend le compteur eligible aux alertes.</p></div></div>
          <div class="item"><div class="date">Etape 3</div><div><strong>Alerte</strong><p>Une baisse de solde declenche un calcul de jours restants et un SMS.</p></div></div>
          <div class="item"><div class="date">Etape 4</div><div><strong>Suivi</strong><p>Le dashboard affiche abonnement, paiement, SMS, anti-doublon et historique.</p></div></div>
        </div>
      </div>

      <div class="panel span-12">
        <h2>Plan de mise en ligne partenaire</h2>
        <table>
          <thead><tr><th>Lot</th><th>Objectif</th><th>Preuve attendue</th><th>Statut</th></tr></thead>
          <tbody>
            <tr><td>Lot 1</td><td>Demo locale stable</td><td>Script demo + dashboard + fiche compteur</td><td>Termine</td></tr>
            <tr><td>Lot 2</td><td>Acces partenaire protege</td><td>Token admin + URL partageable</td><td>En cours</td></tr>
            <tr><td>Lot 3</td><td>SMS reel</td><td>Fournisseur configure, test bout en bout</td><td>A faire</td></tr>
            <tr><td>Lot 4</td><td>Donnees SEEG pilote</td><td>Format webhook ou fichier EDAN valide</td><td>A faire</td></tr>
            <tr><td>Lot 5</td><td>Hebergement pilote</td><td>HTTPS, sauvegarde DB, monitoring</td><td>A faire</td></tr>
          </tbody>
        </table>
      </div>

      <div class="panel span-6">
        <h2>Ce que les partenaires peuvent verifier</h2>
        <p>Le partenaire peut suivre le flux complet : compteur souscrit, paiement confirme, alerte faible, SMS genere, doublon bloque, historique visible.</p>
      </div>
      <div class="panel span-6">
        <h2>Decisions a prendre</h2>
        <p>Choisir le fournisseur SMS, definir le format exact des donnees SEEG, choisir l'hebergement pilote et valider le niveau d'acces partenaire.</p>
      </div>
    </section>
  </main>
</body>
</html>"""

    def architecture_html(self) -> str:
        return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(settings.app_name)} - Architecture</title>
  <style>
    body {{ font-family:"Segoe UI", Arial, sans-serif; margin:0; background:#f4f7f8; color:#142126; }}
    header {{ background:linear-gradient(135deg, #173f49, #0b6b4f); color:white; padding:22px 28px; }}
    main {{ max-width:1180px; margin:0 auto; padding:22px 28px 34px; }}
    h1 {{ margin:0 0 6px; font-size:28px; }}
    h2 {{ margin:24px 0 12px; font-size:19px; }}
    .panel {{ background:white; border:1px solid #d8e1e4; border-radius:8px; padding:18px; margin-bottom:16px; box-shadow:0 8px 20px rgba(20,33,38,.04); }}
    .flow {{ display:grid; grid-template-columns:repeat(5, 1fr); gap:10px; align-items:stretch; }}
    .step {{ border:1px solid #d8e1e4; border-radius:8px; padding:14px; background:#fbfdfd; }}
    .step strong {{ display:block; margin-bottom:8px; color:#0b6b4f; }}
    ol li {{ margin:10px 0; }}
    code {{ background:#eef5f3; padding:2px 5px; border-radius:4px; }}
    a {{ color:#0b6b4f; }}
    svg {{ width:100%; height:auto; background:white; border:1px solid #d8e1e4; border-radius:8px; }}
    @media (max-width:900px) {{ .flow {{ grid-template-columns:1fr; }} main {{ padding:16px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(settings.app_name)} - Architecture fonctionnelle</h1>
    <div>Comprendre ce qui se passe derriere le dashboard.</div>
  </header>
  <main>
    <p><a href="{self.admin_link("/dashboard")}">Retour au tableau de bord</a></p>
    <section class="panel">
      <h2>Vue d'ensemble</h2>
      <div class="flow">
        <div class="step"><strong>Client</strong>Souscrit au service et associe son compteur a un numero mobile.</div>
        <div class="step"><strong>SEEG</strong>Envoie des webhooks HTTP vers SEEG Protect.</div>
        <div class="step"><strong>API</strong>Verifie la signature, valide le JSON et declenche la logique metier.</div>
        <div class="step"><strong>Stockage</strong>Conserve abonnements, paiements, notifications et evenements.</div>
        <div class="step"><strong>SMS</strong>Simule l'envoi dans l'outbox ou appelle un fournisseur SMS reel.</div>
      </div>
    </section>
    <section class="panel">
      <h2>Schema technique</h2>
      {self.architecture_svg()}
    </section>
    <section class="panel">
      <h2>Scenario exemple</h2>
      <ol>
        <li>Un client demande l'activation de SEEG Protect pour son compteur <code>api-meter-...</code>.</li>
        <li>La SEEG appelle <code>POST /webhooks/subscriptions</code>. Le service cree une souscription en attente de paiement.</li>
        <li>Apres paiement, la SEEG appelle <code>POST /webhooks/payments</code>. La souscription passe a <code>active</code>.</li>
        <li>Quand le solde est faible, la SEEG appelle <code>POST /webhooks/low-balance</code> avec le solde restant.</li>
        <li>SEEG Protect calcule les jours restants, verifie l'anti-doublon, puis cree un SMS.</li>
        <li>En mode demo, le SMS est ecrit dans <code>logs/sms_outbox.jsonl</code>. En production, il part vers le fournisseur SMS.</li>
        <li>Le dashboard lit SQLite et affiche les resultats : compteur actif, paiement, SMS, evenements.</li>
      </ol>
    </section>
    <section class="panel">
      <h2>Point important</h2>
      <p>Il n'y a pas d'appel telephonique vocal dans ce MVP. Les "appels" sont des appels HTTP entre systemes. Le client recoit un SMS, pas un appel vocal.</p>
    </section>
  </main>
</body>
</html>"""

    @staticmethod
    def stat_html(label: str, value: int | str) -> str:
        return f'<div class="stat span-3"><div class="label">{escape(label)}</div><div class="value">{escape(str(value))}</div></div>'

    @staticmethod
    def hidden_token_input() -> str:
        if not settings.admin_token:
            return ""
        return f'<input type="hidden" name="token" value="{escape(settings.admin_token)}">'

    @staticmethod
    def bar_chart_html(rows: list[dict[str, Any]], label_key: str) -> str:
        if not rows:
            return '<p class="subtle">Aucune donnee disponible.</p>'
        max_value = max(int(row["total"]) for row in rows) or 1
        parts = []
        for row in rows:
            label = str(row.get(label_key) or "inconnu")
            total = int(row["total"])
            width = max(4, round((total / max_value) * 100))
            parts.append(
                f'<div class="bar-row"><span>{escape(label)}</span>'
                f'<div class="bar-track"><div class="bar-fill" style="width:{width}%"></div></div>'
                f'<strong>{total}</strong></div>'
            )
        return "".join(parts)

    @staticmethod
    def timeline_html(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return '<p class="subtle">Aucun SMS enregistre.</p>'
        max_value = max(int(row["total"]) for row in rows) or 1
        parts = []
        for row in rows:
            total = int(row["total"])
            height = max(6, round((total / max_value) * 130))
            label = str(row["day"])[5:]
            parts.append(
                f'<div class="day"><div class="day-bar" title="{total} SMS" style="height:{height}px"></div>'
                f'<div class="day-label">{escape(label)}</div></div>'
            )
        return f'<div class="timeline">{"".join(parts)}</div>'

    @staticmethod
    def donut_chart_html(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return '<p class="subtle">Aucun statut SMS disponible.</p>'
        total = sum(int(row["total"]) for row in rows) or 1
        first = rows[0]
        first_value = int(first["total"])
        first_percent = round((first_value / total) * 100)
        legend = []
        for row in rows:
            label = str(row.get("status") or "inconnu")
            value = int(row["total"])
            percent = round((value / total) * 100)
            legend.append(
                f'<div class="bar-row"><span>{escape(label)}</span>'
                f'<div class="bar-track"><div class="bar-fill" style="width:{max(4, percent)}%"></div></div>'
                f'<strong>{value}</strong></div>'
            )
        return (
            '<div style="display:grid;grid-template-columns:130px 1fr;gap:16px;align-items:center">'
            f'<div style="width:120px;height:120px;border-radius:50%;background:conic-gradient(#0b6b4f 0 {first_percent}%, #dfe8eb {first_percent}% 100%);display:grid;place-items:center">'
            f'<div style="width:76px;height:76px;border-radius:50%;background:white;display:grid;place-items:center;font-weight:800;color:#0b6b4f">{total}</div>'
            '</div>'
            f'<div>{"".join(legend)}</div>'
            '</div>'
        )

    @staticmethod
    def progress_html(label: str, percent: int) -> str:
        safe_percent = max(0, min(percent, 100))
        return (
            f'<div style="margin:10px 0"><div style="display:flex;justify-content:space-between;gap:12px">'
            f'<strong>{escape(label)}</strong><span>{safe_percent}%</span></div>'
            f'<div class="bar"><div class="fill" style="width:{safe_percent}%"></div></div></div>'
        )

    @staticmethod
    def architecture_svg() -> str:
        return """<svg viewBox="0 0 1120 420" role="img" aria-label="Architecture SEEG Protect">
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">
      <path d="M0,0 L0,6 L9,3 z" fill="#0b6b4f" />
    </marker>
  </defs>
  <rect x="40" y="60" width="160" height="80" rx="8" fill="#eef5f3" stroke="#0b6b4f"/>
  <text x="120" y="92" text-anchor="middle" font-size="16" font-weight="700" fill="#142126">Client</text>
  <text x="120" y="116" text-anchor="middle" font-size="12" fill="#56666d">numero mobile</text>
  <rect x="270" y="60" width="170" height="80" rx="8" fill="#ffffff" stroke="#0b6b4f"/>
  <text x="355" y="92" text-anchor="middle" font-size="16" font-weight="700" fill="#142126">Systeme SEEG</text>
  <text x="355" y="116" text-anchor="middle" font-size="12" fill="#56666d">webhooks HTTP signes</text>
  <rect x="510" y="60" width="170" height="80" rx="8" fill="#ffffff" stroke="#0b6b4f"/>
  <text x="595" y="88" text-anchor="middle" font-size="16" font-weight="700" fill="#142126">API SEEG Protect</text>
  <text x="595" y="112" text-anchor="middle" font-size="12" fill="#56666d">validation + metier</text>
  <rect x="750" y="60" width="150" height="80" rx="8" fill="#ffffff" stroke="#0b6b4f"/>
  <text x="825" y="92" text-anchor="middle" font-size="16" font-weight="700" fill="#142126">SQLite</text>
  <text x="825" y="116" text-anchor="middle" font-size="12" fill="#56666d">donnees + logs</text>
  <rect x="960" y="60" width="130" height="80" rx="8" fill="#eef5f3" stroke="#0b6b4f"/>
  <text x="1025" y="92" text-anchor="middle" font-size="16" font-weight="700" fill="#142126">Dashboard</text>
  <text x="1025" y="116" text-anchor="middle" font-size="12" fill="#56666d">suivi metier</text>
  <rect x="510" y="245" width="170" height="80" rx="8" fill="#fff8eb" stroke="#c47a00"/>
  <text x="595" y="278" text-anchor="middle" font-size="16" font-weight="700" fill="#142126">SMS Gateway</text>
  <text x="595" y="302" text-anchor="middle" font-size="12" fill="#56666d">stub ou fournisseur</text>
  <rect x="750" y="245" width="150" height="80" rx="8" fill="#fff8eb" stroke="#c47a00"/>
  <text x="825" y="278" text-anchor="middle" font-size="16" font-weight="700" fill="#142126">Outbox SMS</text>
  <text x="825" y="302" text-anchor="middle" font-size="12" fill="#56666d">sms_outbox.jsonl</text>
  <line x1="200" y1="100" x2="270" y2="100" stroke="#0b6b4f" stroke-width="3" marker-end="url(#arrow)"/>
  <line x1="440" y1="100" x2="510" y2="100" stroke="#0b6b4f" stroke-width="3" marker-end="url(#arrow)"/>
  <line x1="680" y1="100" x2="750" y2="100" stroke="#0b6b4f" stroke-width="3" marker-end="url(#arrow)"/>
  <line x1="900" y1="100" x2="960" y2="100" stroke="#0b6b4f" stroke-width="3" marker-end="url(#arrow)"/>
  <line x1="595" y1="140" x2="595" y2="245" stroke="#c47a00" stroke-width="3" marker-end="url(#arrow)"/>
  <line x1="680" y1="285" x2="750" y2="285" stroke="#c47a00" stroke-width="3" marker-end="url(#arrow)"/>
  <text x="355" y="176" text-anchor="middle" font-size="13" fill="#56666d">subscription / payment / low-balance</text>
  <text x="220" y="46" text-anchor="middle" font-size="13" fill="#56666d">Le client agit dans le parcours SEEG</text>
  <text x="708" y="214" text-anchor="middle" font-size="13" fill="#56666d">Notification apres calcul des jours restants</text>
</svg>"""

    @staticmethod
    def table_html(rows: list[dict[str, Any]], columns: list[str]) -> str:
        if not rows:
            return "<p>Aucune donnee.</p>"
        head = "".join(f"<th>{escape(column)}</th>" for column in columns)
        body_rows = []
        for row in rows:
            cells = "".join(f"<td>{escape(str(row.get(column) or ''))}</td>" for column in columns)
            body_rows.append(f"<tr>{cells}</tr>")
        return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"

    def log_message(self, format: str, *args: Any) -> None:
        return


def run() -> None:
    server = ThreadingHTTPServer((settings.host, settings.port), ApiHandler)
    print(f"SEEG Protect API running on http://{settings.host}:{settings.port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
