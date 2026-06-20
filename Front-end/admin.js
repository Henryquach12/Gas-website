/* ===== Constants ===== */
const DEFAULT_PW    = 'gas2024';
const SESSION_KEY   = 'gas_admin_session';
const PRODUCTS_KEY  = 'gas_products';
const ORDERS_KEY    = 'gas_orders';
const PW_KEY        = 'gas_admin_password';

/* ===== Auth ===== */
function isLoggedIn()   { return sessionStorage.getItem(SESSION_KEY) === '1'; }
function storedPw()     { return localStorage.getItem(PW_KEY) || DEFAULT_PW; }

function login(pw) {
  if (pw !== storedPw()) return false;
  sessionStorage.setItem(SESSION_KEY, '1');
  return true;
}

function logout() {
  sessionStorage.removeItem(SESSION_KEY);
  document.getElementById('adminPanel').hidden = true;
  document.getElementById('loginGate').hidden  = false;
  document.getElementById('loginPassword').value = '';
  document.getElementById('loginError').textContent = '';
}

/* ===== Login form ===== */
document.getElementById('loginForm').addEventListener('submit', (e) => {
  e.preventDefault();
  const pw  = document.getElementById('loginPassword').value;
  const err = document.getElementById('loginError');
  if (login(pw)) {
    err.textContent = '';
    showAdminPanel();
  } else {
    err.textContent = 'Mật khẩu không đúng.';
    document.getElementById('loginPassword').classList.add('error');
  }
});

document.getElementById('logoutBtn').addEventListener('click', logout);

function showAdminPanel() {
  document.getElementById('loginGate').hidden  = true;
  document.getElementById('adminPanel').hidden = false;
  renderProductList();
  renderOrderList();
}

/* ===== Tabs ===== */
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  });
});

/* ===== Storage helpers ===== */
function getProducts() {
  try { return JSON.parse(localStorage.getItem(PRODUCTS_KEY) || '[]'); }
  catch { return []; }
}

function saveProducts(list) {
  localStorage.setItem(PRODUCTS_KEY, JSON.stringify(list));
}

function getOrders() {
  try { return JSON.parse(localStorage.getItem(ORDERS_KEY) || '[]'); }
  catch { return []; }
}

function saveOrders(list) {
  localStorage.setItem(ORDERS_KEY, JSON.stringify(list));
}

function formatPrice(p) {
  return Number(p).toLocaleString('vi-VN') + 'đ';
}

function escHtml(str) {
  return String(str)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ===== Image upload ===== */
let currentImageBase64 = null;

const uploadArea     = document.getElementById('imageUploadArea');
const fileInput      = document.getElementById('productImage');
const previewImg     = document.getElementById('imagePreview');
const placeholder    = document.getElementById('imageUploadPlaceholder');
const removeBtn      = document.getElementById('removeImageBtn');

uploadArea.addEventListener('click', (e) => {
  if (e.target === removeBtn || removeBtn.contains(e.target)) return;
  fileInput.click();
});

uploadArea.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); }
});

fileInput.addEventListener('change', () => {
  const file = fileInput.files[0];
  if (!file) return;
  const imgErrEl = document.getElementById('productImageError');

  if (file.size > 5 * 1024 * 1024) {
    imgErrEl.textContent = 'Ảnh quá lớn — tối đa 5MB.';
    fileInput.value = '';
    return;
  }
  imgErrEl.textContent = '';

  const reader = new FileReader();
  reader.onload = (ev) => {
    currentImageBase64 = ev.target.result;
    previewImg.src       = currentImageBase64;
    previewImg.style.display   = 'block';
    placeholder.style.display  = 'none';
    removeBtn.style.display    = 'block';
  };
  reader.readAsDataURL(file);
});

removeBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  clearImage();
});

function clearImage() {
  currentImageBase64         = null;
  fileInput.value            = '';
  previewImg.src             = '';
  previewImg.style.display   = 'none';
  placeholder.style.display  = 'flex';
  removeBtn.style.display    = 'none';
}

function setImageFromUrl(src) {
  if (!src) { clearImage(); return; }
  currentImageBase64         = src;
  previewImg.src             = src;
  previewImg.style.display   = 'block';
  placeholder.style.display  = 'none';
  removeBtn.style.display    = 'block';
}

/* ===== Product form validation ===== */
function validateProductForm() {
  let ok = true;

  const name = document.getElementById('productName').value.trim();
  const nameErr = document.getElementById('productNameError');
  if (name.length < 2) {
    nameErr.textContent = 'Tên sản phẩm phải ít nhất 2 ký tự.';
    document.getElementById('productName').classList.add('error');
    ok = false;
  } else {
    nameErr.textContent = '';
    document.getElementById('productName').classList.remove('error');
  }

  const cat    = document.getElementById('productCategory').value;
  const catErr = document.getElementById('productCategoryError');
  if (!cat) {
    catErr.textContent = 'Vui lòng chọn danh mục.';
    ok = false;
  } else {
    catErr.textContent = '';
  }

  const price    = parseFloat(document.getElementById('productPrice').value);
  const priceErr = document.getElementById('productPriceError');
  if (isNaN(price) || price < 0) {
    priceErr.textContent = 'Vui lòng nhập giá hợp lệ.';
    document.getElementById('productPrice').classList.add('error');
    ok = false;
  } else {
    priceErr.textContent = '';
    document.getElementById('productPrice').classList.remove('error');
  }

  return ok;
}

/* ===== Add / Edit product ===== */
let editingId = null;

document.getElementById('productForm').addEventListener('submit', (e) => {
  e.preventDefault();
  if (!validateProductForm()) return;

  const name        = document.getElementById('productName').value.trim();
  const category    = document.getElementById('productCategory').value;
  const price       = parseFloat(document.getElementById('productPrice').value);
  const stockRaw    = document.getElementById('productStock').value.trim();
  const description = document.getElementById('productDesc').value.trim();
  const stock       = stockRaw !== '' ? parseInt(stockRaw, 10) : null;

  const products = getProducts();

  if (editingId) {
    const idx = products.findIndex(p => p.id === editingId);
    if (idx !== -1) {
      products[idx] = {
        ...products[idx],
        name, category, price, stock, description,
        image: currentImageBase64 !== null ? currentImageBase64 : products[idx].image,
        updatedAt: new Date().toISOString(),
      };
      saveProducts(products);
      showToast('Đã cập nhật sản phẩm!');
      cancelEdit();
    }
  } else {
    products.push({
      id: 'prod_' + Date.now(),
      name, category, price, stock, description,
      image: currentImageBase64 || null,
      createdAt: new Date().toISOString(),
    });
    saveProducts(products);
    showToast('Đã thêm sản phẩm!');
    document.getElementById('productForm').reset();
    clearImage();
  }

  renderProductList();
});

function startEdit(productId) {
  const p = getProducts().find(x => x.id === productId);
  if (!p) return;

  editingId = productId;
  document.getElementById('editProductId').value          = productId;
  document.getElementById('productName').value            = p.name;
  document.getElementById('productCategory').value        = p.category;
  document.getElementById('productPrice').value           = p.price;
  document.getElementById('productStock').value           = p.stock ?? '';
  document.getElementById('productDesc').value            = p.description || '';
  setImageFromUrl(p.image || null);

  document.getElementById('productFormTitle').textContent  = 'Chỉnh Sửa Sản Phẩm';
  document.getElementById('productSubmitBtn').textContent  = 'Lưu Thay Đổi';
  document.getElementById('cancelEditBtn').hidden          = false;

  document.getElementById('productForm').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function cancelEdit() {
  editingId = null;
  document.getElementById('productForm').reset();
  clearImage();
  document.getElementById('productFormTitle').textContent = 'Thêm Sản Phẩm Mới';
  document.getElementById('productSubmitBtn').textContent = 'Thêm Sản Phẩm';
  document.getElementById('cancelEditBtn').hidden         = true;
  ['productNameError','productCategoryError','productPriceError'].forEach(id => {
    document.getElementById(id).textContent = '';
  });
  ['productName','productPrice'].forEach(id => {
    document.getElementById(id).classList.remove('error','valid');
  });
}

document.getElementById('cancelEditBtn').addEventListener('click', cancelEdit);

/* ===== Delete product ===== */
let deleteTargetId = null;

function confirmDelete(productId) {
  deleteTargetId = productId;
  document.getElementById('deleteModal').classList.add('open');
  document.body.style.overflow = 'hidden';
}

document.getElementById('cancelDeleteBtn').addEventListener('click', () => {
  document.getElementById('deleteModal').classList.remove('open');
  document.body.style.overflow = '';
  deleteTargetId = null;
});

document.getElementById('confirmDeleteBtn').addEventListener('click', () => {
  if (!deleteTargetId) return;
  saveProducts(getProducts().filter(p => p.id !== deleteTargetId));
  deleteTargetId = null;
  document.getElementById('deleteModal').classList.remove('open');
  document.body.style.overflow = '';
  renderProductList();
  showToast('Đã xóa sản phẩm.');
});

/* ===== Render product list ===== */
function renderProductList() {
  const products = getProducts();
  document.getElementById('productCount').textContent = `${products.length} sản phẩm`;
  const list = document.getElementById('adminProductList');

  if (products.length === 0) {
    list.innerHTML = `<div class="admin-empty"><span class="empty-icon">🛢️</span><p>Chưa có sản phẩm nào. Thêm sản phẩm bên trên.</p></div>`;
    return;
  }

  list.innerHTML = products.map(p => `
    <div class="admin-product-item">
      ${p.image
        ? `<img class="admin-product-img" src="${escHtml(p.image)}" alt="${escHtml(p.name)}">`
        : `<div class="admin-product-img-placeholder">🛢️</div>`}
      <div class="admin-product-info">
        <div class="admin-product-name">${escHtml(p.name)}</div>
        <div class="admin-product-meta">${escHtml(p.category)}${p.stock != null ? ` · Tồn: ${p.stock}` : ''}</div>
      </div>
      <div class="admin-product-price">${formatPrice(p.price)}</div>
      <div class="admin-product-actions">
        <button class="edit-btn"   onclick="startEdit('${escHtml(p.id)}')">Sửa</button>
        <button class="delete-btn" onclick="confirmDelete('${escHtml(p.id)}')">Xóa</button>
      </div>
    </div>
  `).join('');
}

/* ===== Render order list ===== */
function renderOrderList() {
  const orders = getOrders();
  const list   = document.getElementById('adminOrderList');

  if (orders.length === 0) {
    list.innerHTML = `<div class="admin-empty"><span class="empty-icon">📋</span><p>Chưa có đơn hàng nào.</p></div>`;
    return;
  }

  list.innerHTML = orders.map(o => {
    const date = new Date(o.createdAt).toLocaleString('vi-VN');
    return `
      <div class="admin-order-item">
        <div class="order-header">
          <div>
            <div class="order-product">${escHtml(o.productName)} × ${o.qty}</div>
            <div class="order-total">${formatPrice(o.total)}</div>
          </div>
          <span class="order-status">${escHtml(o.status)}</span>
        </div>
        <div class="order-customer">
          <span>👤 ${escHtml(o.customerName)}</span>
          <span>📞 ${escHtml(o.phone)}</span>
          <span>📍 ${escHtml(o.address)}</span>
          ${o.note ? `<span class="order-note">📝 ${escHtml(o.note)}</span>` : ''}
        </div>
        <div class="order-meta">
          <span class="order-id">Mã: ${escHtml(o.id)}</span>
          <span class="order-date">${date}</span>
        </div>
      </div>
    `;
  }).join('');
}

/* ===== Clear orders ===== */
document.getElementById('clearOrdersBtn').addEventListener('click', () => {
  if (!confirm('Xóa toàn bộ đơn hàng? Không thể hoàn tác.')) return;
  saveOrders([]);
  renderOrderList();
  showToast('Đã xóa tất cả đơn hàng.');
});

/* ===== Toast ===== */
function showToast(msg, ms = 3000) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), ms);
}

/* ===== Init ===== */
if (isLoggedIn()) {
  showAdminPanel();
}
