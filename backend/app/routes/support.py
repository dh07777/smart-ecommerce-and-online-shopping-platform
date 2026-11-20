from flask import Blueprint, g, jsonify, request

from ..extensions import db
from ..models import Notification, SupportTicket, TicketMessage
from ..services import notify_staff
from ..utils import (api_error, auth_required, clean, optional_user, paginate, rate_limit, valid_email)

bp = Blueprint("support", __name__, url_prefix="/api")


@bp.post("/support/contact")
@rate_limit(5)
def contact():
    d = request.get_json(silent=True) or {}
    user = optional_user()
    name = clean(d.get("name"), 120) or (user.name if user else "")
    email = clean(d.get("email")).lower() or (user.email if user else "")
    subject, message = clean(d.get("subject"), 200), clean(d.get("message"), 3000)
    if not valid_email(email):
        return api_error("Please enter a valid email")
    if len(subject) < 3 or len(message) < 10:
        return api_error("Please add a subject and a message (at least 10 characters)")
    t = SupportTicket(user_id=user.id if user else None, name=name, email=email, subject=subject)
    t.messages.append(TicketMessage(sender="customer", body=message))
    db.session.add(t)
    notify_staff("New support ticket", f"#{t.id or 'new'}: {subject}", "support")
    db.session.commit()
    return jsonify(t.to_dict(detail=True)), 201


@bp.get("/support/tickets")
@auth_required
def my_tickets():
    q = SupportTicket.query.filter_by(user_id=g.user.id).order_by(SupportTicket.created_at.desc())
    return jsonify(paginate(q, lambda t: t.to_dict()))


@bp.get("/support/tickets/<int:tid>")
@auth_required
def ticket_detail(tid):
    t = SupportTicket.query.filter_by(id=tid, user_id=g.user.id).first_or_404()
    return jsonify(t.to_dict(detail=True))


@bp.post("/support/tickets/<int:tid>/reply")
@auth_required
def ticket_reply(tid):
    t = SupportTicket.query.filter_by(id=tid, user_id=g.user.id).first_or_404()
    body = clean((request.get_json(silent=True) or {}).get("message"), 3000)
    if len(body) < 2:
        return api_error("Message is empty")
    if t.status in ("resolved", "closed"):
        t.status = "open"
    t.messages.append(TicketMessage(sender="customer", body=body))
    db.session.commit()
    return jsonify(t.to_dict(detail=True))


# ---------------- notifications ----------------
@bp.get("/notifications")
@auth_required
def notifications():
    q = Notification.query.filter_by(user_id=g.user.id).order_by(Notification.created_at.desc())
    data = paginate(q, lambda n: n.to_dict())
    data["unread"] = Notification.query.filter_by(user_id=g.user.id, is_read=False).count()
    return jsonify(data)


@bp.get("/notifications/unread-count")
@auth_required
def unread_count():
    return jsonify({"unread": Notification.query.filter_by(user_id=g.user.id, is_read=False).count()})


@bp.patch("/notifications/<int:nid>/read")
@auth_required
def mark_read(nid):
    n = Notification.query.filter_by(id=nid, user_id=g.user.id).first_or_404()
    n.is_read = True
    db.session.commit()
    return jsonify(n.to_dict())


@bp.post("/notifications/read-all")
@auth_required
def read_all():
    Notification.query.filter_by(user_id=g.user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"message": "All notifications marked as read"})
