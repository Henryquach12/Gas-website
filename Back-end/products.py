"""
Products blueprint (public reads + admin writes).

Endpoints
---------
GET  /api/products           – list active products (public)
GET  /api/products/<id>      – single product (public)
POST /api/products           – create product (admin)
PUT  /api/products/<id>      – update product (admin)
DELETE /api/products/<id>    – soft-delete product (admin)
"""
from flask import Blueprint, request, jsonify
from marshmallow import Schema, fields, validate, ValidationError

from models import db, Product
from utils import sanitize, audit, admin_required

products_bp = Blueprint("products", __name__, url_prefix="/api/products")

ALLOWED_CATEGORIES = ["Bình Gas", "Bếp Gas", "Bình Nước", "Nệm", "Phụ Kiện"]


# ── Schemas ────────────────────────────────────────────────────────────────────

def _validate_image(value):
    if value is None:
        return
    if value.startswith("data:image/") or value.startswith("https://"):
        return
    raise validate.ValidationError("Phải là URL https:// hoặc ảnh tải lên (data:image/...).")


class ProductSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=2, max=255))
    category = fields.Str(required=True, validate=validate.OneOf(ALLOWED_CATEGORIES))
    price = fields.Decimal(required=True, places=0)
    stock = fields.Int(load_default=None, validate=validate.Range(min=0))
    description = fields.Str(load_default=None, validate=validate.Length(max=2000))
    image_url = fields.Str(load_default=None, validate=_validate_image)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _product_to_dict(p: Product) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "category": p.category,
        "price": str(p.price),
        "stock": p.stock,
        "description": p.description,
        "image_url": p.image_url,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


# ── Public routes ──────────────────────────────────────────────────────────────

@products_bp.get("/")
def list_products():
    category = request.args.get("category")
    query = Product.query.filter_by(is_active=True)
    if category and category in ALLOWED_CATEGORIES:
        query = query.filter_by(category=category)
    products = query.order_by(Product.name).all()
    return jsonify({"products": [_product_to_dict(p) for p in products]}), 200


@products_bp.get("/<int:product_id>")
def get_product(product_id: int):
    p = Product.query.filter_by(id=product_id, is_active=True).first_or_404()
    return jsonify(_product_to_dict(p)), 200


# ── Admin routes ───────────────────────────────────────────────────────────────

@products_bp.post("/")
@admin_required
def create_product():
    try:
        data = ProductSchema().load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": "Validation failed", "details": e.messages}), 422

    product = Product(
        name=sanitize(data["name"]),
        category=data["category"],
        price=data["price"],
        stock=data.get("stock"),
        description=sanitize(data.get("description") or ""),
        image_url=data.get("image_url"),
    )
    db.session.add(product)
    db.session.commit()
    audit("product_create", {"product_id": product.id, "name": product.name})
    return jsonify(_product_to_dict(product)), 201


@products_bp.put("/<int:product_id>")
@admin_required
def update_product(product_id: int):
    product = db.session.get(Product, product_id)
    if not product or not product.is_active:
        return jsonify({"error": "Product not found."}), 404

    try:
        data = ProductSchema(partial=True).load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": "Validation failed", "details": e.messages}), 422

    if "name" in data:
        product.name = sanitize(data["name"])
    if "category" in data:
        product.category = data["category"]
    if "price" in data:
        product.price = data["price"]
    if "stock" in data:
        product.stock = data["stock"]
    if "description" in data:
        product.description = sanitize(data["description"] or "")
    if "image_url" in data:
        product.image_url = data["image_url"]

    db.session.commit()
    audit("product_update", {"product_id": product_id})
    return jsonify(_product_to_dict(product)), 200


@products_bp.delete("/<int:product_id>")
@admin_required
def delete_product(product_id: int):
    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({"error": "Product not found."}), 404
    product.is_active = False
    db.session.commit()
    audit("product_delete", {"product_id": product_id})
    return jsonify({"message": "Product deactivated."}), 200
