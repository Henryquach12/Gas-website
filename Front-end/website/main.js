/* ===== Navbar scroll ===== */
const navbar = document.getElementById('navbar');
window.addEventListener('scroll', () => {
  navbar.classList.toggle('scrolled', window.scrollY > 20);
  updateActiveLink();
});

/* ===== Hamburger ===== */
const hamburger = document.querySelector('.hamburger');
const navLinks  = document.querySelector('.nav-links');

hamburger.addEventListener('click', () => {
  hamburger.classList.toggle('open');
  navLinks.classList.toggle('open');
});

navLinks.addEventListener('click', (e) => {
  if (e.target.tagName === 'A' && !e.target.closest('.nav-dropdown')) {
    hamburger.classList.remove('open');
    navLinks.classList.remove('open');
  }
});

/* ===== Active nav link ===== */
function updateActiveLink() {
  const sections = document.querySelectorAll('section[id]');
  const links    = document.querySelectorAll('.nav-links > li > a');
  let current    = '';
  sections.forEach(s => { if (window.scrollY >= s.offsetTop - 100) current = s.id; });
  links.forEach(l => {
    l.classList.remove('active');
    if (l.getAttribute('href') === `#${current}`) l.classList.add('active');
  });
}

/* ===== Nav dropdown ===== */
const dropdownItem   = document.querySelector('.has-dropdown');
const dropdownTrigger = document.querySelector('.dropdown-trigger');

dropdownTrigger.addEventListener('click', (e) => {
  if (window.innerWidth <= 640) {
    e.preventDefault();
    dropdownItem.classList.toggle('open');
  }
});

document.querySelectorAll('.nav-dropdown a[data-cat]').forEach(link => {
  link.addEventListener('click', (e) => {
    e.preventDefault();
    setFilter(link.dataset.cat);
    dropdownItem.classList.remove('open');
    hamburger.classList.remove('open');
    navLinks.classList.remove('open');
    document.getElementById('products').scrollIntoView({ behavior: 'smooth' });
  });
});

/* ===== Filter state ===== */
let activeFilter = '';

function setFilter(cat) {
  activeFilter = cat;
  const bar = document.getElementById('filterBar');
  const tag = document.getElementById('filterTag');
  if (cat) {
    tag.textContent   = cat;
    bar.style.display = 'flex';
  } else {
    bar.style.display = 'none';
  }
  renderProducts();
}

document.getElementById('filterClear').addEventListener('click', () => setFilter(''));

/* ===== Fade-in observer ===== */
const fadeObserver = new IntersectionObserver(
  (entries) => entries.forEach(e => {
    if (e.isIntersecting) {
      e.target.style.opacity = '1';
      e.target.style.transform = 'translateY(0)';
      fadeObserver.unobserve(e.target);
    }
  }),
  { threshold: 0.1 }
);

/* ===== Storage ===== */
function getProducts() {
  try { return JSON.parse(localStorage.getItem('gas_products') || '[]'); }
  catch { return []; }
}

function saveOrder(order) {
  try {
    const orders = JSON.parse(localStorage.getItem('gas_orders') || '[]');
    orders.unshift(order);
    localStorage.setItem('gas_orders', JSON.stringify(orders));
  } catch { /* ignore */ }
}

/* ===== Helpers ===== */
function formatPrice(price) {
  return Number(price).toLocaleString('vi-VN') + 'đ';
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function catIcon(cat) {
  if (!cat) return '🛒';
  if (cat === 'Bình Gas') return '🛢️';
  if (cat === 'Bếp Gas')  return '🔥';
  if (cat === 'Bình Nước') return '💧';
  if (cat === 'Nệm')      return '🛏️';
  return '📦';
}

/* ===== Render products ===== */
function renderProducts() {
  const grid    = document.getElementById('productsGrid');
  const all     = getProducts();
  const visible = activeFilter ? all.filter(p => p.category === activeFilter) : all;

  if (all.length === 0) {
    grid.innerHTML = `
      <div class="products-empty">
        <div class="empty-icon">🛒</div>
        <h3>Sản phẩm đang được cập nhật</h3>
        <p>Vui lòng liên hệ trực tiếp hoặc quay lại sau.</p>
      </div>`;
    return;
  }

  if (visible.length === 0) {
    grid.innerHTML = `
      <div class="products-empty">
        <div class="empty-icon">${catIcon(activeFilter)}</div>
        <h3>Không có sản phẩm trong danh mục này</h3>
        <p><button onclick="setFilter('')" style="background:none;border:1.5px solid #2563eb;color:#2563eb;border-radius:8px;padding:.4rem 1rem;cursor:pointer;font-weight:600">Xem tất cả sản phẩm</button></p>
      </div>`;
    return;
  }

  grid.innerHTML = visible.map(p => `
    <div class="product-card">
      ${p.image
        ? `<img class="product-img" src="${escHtml(p.image)}" alt="${escHtml(p.name)}">`
        : `<div class="product-img-placeholder">${catIcon(p.category)}</div>`}
      <div class="product-body">
        <div class="product-category">${escHtml(p.category || 'Sản phẩm')}</div>
        <div class="product-name">${escHtml(p.name)}</div>
        <div class="product-desc">${escHtml(p.description || '')}</div>
        <div class="product-price">${formatPrice(p.price)}</div>
        <button class="product-order-btn" data-id="${escHtml(p.id)}">Đặt Hàng</button>
      </div>
    </div>
  `).join('');

  grid.querySelectorAll('.product-card').forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(24px)';
    el.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
    fadeObserver.observe(el);
  });

  grid.querySelectorAll('.product-order-btn').forEach(btn => {
    btn.addEventListener('click', () => openOrderModal(btn.dataset.id));
  });
}

/* ===== Order modal ===== */
let currentProductId = null;

function openOrderModal(productId) {
  const p = getProducts().find(x => x.id === productId);
  if (!p) return;
  currentProductId = productId;

  document.getElementById('modalProduct').innerHTML = `
    ${p.image
      ? `<img src="${escHtml(p.image)}" alt="${escHtml(p.name)}">`
      : `<div class="modal-product-placeholder">${catIcon(p.category)}</div>`}
    <div>
      <div class="modal-product-name">${escHtml(p.name)}</div>
      <div class="modal-product-price">${formatPrice(p.price)}</div>
    </div>`;

  document.getElementById('orderForm').reset();
  document.getElementById('orderQty').value = 1;
  clearAllErrors();
  openModal('orderModal');
}

function openModal(id) {
  document.getElementById(id).classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeModal(id) {
  document.getElementById(id).classList.remove('open');
  document.body.style.overflow = '';
}

document.getElementById('modalClose').addEventListener('click', () => closeModal('orderModal'));
document.getElementById('orderModal').addEventListener('click', (e) => {
  if (e.target === document.getElementById('orderModal')) closeModal('orderModal');
});
document.getElementById('successClose').addEventListener('click', () => closeModal('successModal'));

/* ===== Validation ===== */
const PHONE_RE = /^(0[35789])\d{8}$/;

function isLongXuyenAddress(address) {
  const lower = address.toLowerCase();
  return lower.includes('long xuyên') || lower.includes('long xuyen');
}

function markError(inputId, errorId, msg) {
  document.getElementById(inputId).classList.add('error');
  document.getElementById(inputId).classList.remove('valid');
  document.getElementById(errorId).textContent = msg;
  return false;
}

function markValid(inputId, errorId) {
  document.getElementById(inputId).classList.remove('error');
  document.getElementById(inputId).classList.add('valid');
  document.getElementById(errorId).textContent = '';
  return true;
}

function clearAllErrors() {
  [['orderQty','qtyError'],['orderName','nameError'],['orderPhone','phoneError'],['orderAddress','addressError']]
    .forEach(([inp, err]) => {
      document.getElementById(inp).classList.remove('error','valid');
      document.getElementById(err).textContent = '';
    });
}

function validateOrder() {
  let ok = true;

  const qty = parseInt(document.getElementById('orderQty').value, 10);
  if (isNaN(qty) || qty < 1 || qty > 99)
    ok = markError('orderQty', 'qtyError', 'Số lượng phải từ 1 đến 99.');
  else markValid('orderQty', 'qtyError');

  const name = document.getElementById('orderName').value.trim();
  if (name.length < 2)
    ok = markError('orderName', 'nameError', 'Vui lòng nhập họ tên (ít nhất 2 ký tự).');
  else markValid('orderName', 'nameError');

  const phone = document.getElementById('orderPhone').value.trim().replace(/\s/g, '');
  if (!PHONE_RE.test(phone))
    ok = markError('orderPhone', 'phoneError', 'Số điện thoại không hợp lệ (VD: 0901234567).');
  else markValid('orderPhone', 'phoneError');

  const address = document.getElementById('orderAddress').value.trim();
  if (address.length < 10) {
    ok = markError('orderAddress', 'addressError', 'Vui lòng nhập địa chỉ đầy đủ (ít nhất 10 ký tự).');
  } else if (!isLongXuyenAddress(address)) {
    ok = markError('orderAddress', 'addressError',
      'Chúng tôi chỉ giao hàng trong TP. Long Xuyên, An Giang. Vui lòng nhập địa chỉ có "Long Xuyên".');
  } else {
    markValid('orderAddress', 'addressError');
  }

  return ok;
}

// ── Đổi thành URL Render khi deploy, VD: 'https://gas-store-api.onrender.com' ──
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://localhost:5000'
  : 'https://gas-website-mpjm.onrender.com';

/* ===== Submit order ===== */
document.getElementById('orderForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!validateOrder()) return;

  const p = getProducts().find(x => x.id === currentProductId);
  if (!p) return;

  const qty     = parseInt(document.getElementById('orderQty').value, 10);
  const name    = document.getElementById('orderName').value.trim();
  const phone   = document.getElementById('orderPhone').value.trim();
  const address = document.getElementById('orderAddress').value.trim();
  const note    = document.getElementById('orderNote').value.trim();

  // Save locally so the admin panel can still see it
  saveOrder({
    id:           'ord_' + Date.now(),
    productId:    p.id,
    productName:  p.name,
    productPrice: p.price,
    qty,
    total:        p.price * qty,
    customerName: name,
    phone,
    address,
    note,
    status:       'Chờ xác nhận',
    createdAt:    new Date().toISOString(),
  });

  // Notify store owner via SMS through backend
  try {
    await fetch(`${API_BASE}/api/payments/cod`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        customer_name:    name,
        customer_phone:   phone,
        customer_address: address,
        notes:            note,
        product_name:     p.name,
        product_price:    p.price,
        quantity:         qty,
      }),
    });
  } catch {
    // Silent — order is already saved locally; SMS is best-effort
  }

  closeModal('orderModal');
  currentProductId = null;

  document.getElementById('successMsg').textContent =
    `Cảm ơn ${name}! Đơn hàng đã được ghi nhận. Chúng tôi sẽ gọi lại số ${phone} để xác nhận và sắp xếp giao hàng.`;
  openModal('successModal');
});

/* ===== Init ===== */
renderProducts();
