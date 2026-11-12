import { commerceUI, orderExtras } from './commerce-ui.js';
import { api, ApiError, json, money, esc, imagePath } from './api.js';
import { icon } from './icons.js';
import { openVoice } from './speech.js';
import { mountTryOn } from './tryon.js';
import { AmiVoice } from './ami-voice.js';
import { landingPage, toggleLandingMusic } from './landing.js';

/** @type {import('./api.js').Product[]} */
let products = [];
/** @type {import('./api.js').CartLine[]} */
let cart = [];
let categories = [];
let customer = null;
let authDestination = '/shop';
let saved = new Set();
let routeVersion = 0;
let cleanupTryOn = null;
let selectedProduct = null;
let checkoutQuote = null;
let checkoutKey = null;
let chatBusy = false;
let chatRequest = null;
let chatGeneration = 0;
let autoRead = false;
let pendingPaymentId = null;
let toastTimer;
const modal = document.querySelector('#modal');
const statusNames = { pending_payment:'Chờ thanh toán', paid:'Đã thanh toán', expired:'Hết hạn giữ chỗ', payment_failed:'Thanh toán thất bại', reconciliation:'Đang đối soát', confirmed:'Đã xác nhận', processing:'Đang chuẩn bị', shipped:'Đang giao hàng', delivered:'Đã giao hàng', cancelled:'Đã hủy' };
const amiVoice = new AmiVoice(
  value => document.querySelector('#ami-avatar')?.contentWindow?.postMessage({type:'may-ami-mouth',value},location.origin),
  state => {
    const status=document.querySelector('#chat-status');
    if(status)status.textContent=state==='loading'?'ElevenLabs đang tạo giọng nói…':state==='speaking'?'Ami đang nói…':chatBusy?'Ami đang xem dữ liệu cửa hàng và suy nghĩ…':'';
    document.querySelector('#ami-stage')?.classList.toggle('is-speaking',state==='speaking');
  },
);
function amiExpression(name) {
  document.querySelector('#ami-avatar')?.contentWindow?.postMessage({type:'may-ami-expression',name},location.origin);
}
const paymentNames = {captured:'Đã xác nhận thanh toán',reconciliation:'Cần đối soát',expired:'Hết hạn',refund_pending:'Đang hoàn tiền',refunded:'Đã hoàn tiền',partially_refunded:'Đã hoàn một phần', pending:'Chưa thanh toán', 'paid-demo':'Đã thanh toán (demo)', 'collected-demo':'Đã thu COD (demo)', failed:'Thanh toán thất bại', cancelled:'Đã dừng thanh toán' };

function toast(message) {
  const el = document.querySelector('#toast');
  el.textContent = message;
  el.classList.add('visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('visible'), 3500);
}

function navigate(path) {
  if (location.hash === '#' + path) renderRoute();
  else location.hash = path;
}

function button(text, action, className = 'secondary', attrs = '') {
  return '<button class="button ' + className + '" data-action="' + action + '" ' + attrs + '>' + text + '</button>';
}

function emptyState(symbol, title, description, action = '<a class="button primary" href="#/shop">Khám phá sản phẩm ' + icon('arrow') + '</a>') {
  return '<div class="empty-state"><span class="empty-icon">' + icon(symbol) + '</span><h2>' + title + '</h2><p>' + description + '</p>' + action + '</div>';
}

function productCard(p) {
  const favorite = saved.has(p.id);
  const discount = p.original_price > p.price ? Math.round((1 - p.price / p.original_price) * 100) : 0;
  return '<article class="product-card"><div class="product-photo">' +
    '<a href="#/product/' + esc(p.id) + '" tabindex="-1" aria-label="' + esc(p.name) + '"><img src="' + imagePath(p.image) + '" alt="' + esc(p.name) + '" width="400" height="500" loading="lazy"></a>' +
    '<span class="product-tag ' + (discount ? 'sale-tag' : '') + '">' + (discount ? '−' + discount + '%' : esc(p.tag || 'Mới về')) + '</span>' +
    '<button class="favorite-button ' + (favorite ? 'is-saved' : '') + '" data-action="favorite" data-id="' + esc(p.id) + '" aria-label="' + (favorite ? 'Bỏ yêu thích ' : 'Yêu thích ') + esc(p.name) + '" aria-pressed="' + favorite + '">' + icon('heart') + '</button>' +
    (p.try_on ? '<a class="try-label" href="#/try-on?product=' + esc(p.id) + '">' + icon('sparkle') + ' Thử phối đồ</a>' : '') +
    '</div><div class="product-info"><p class="product-brand">' + esc(p.brand) + '</p><a class="product-name" href="#/product/' + esc(p.id) + '">' + esc(p.name) + '</a><div class="price-row"><strong>' + money(p.price) + '</strong>' +
    (discount ? '<del>' + money(p.original_price) + '</del>' : '') + '</div><div class="product-bottom"><span>' +
    (p.rating ? icon('star') + ' ' + p.rating : 'Có nguồn sản phẩm') + '</span><a class="small-link" href="#/product/' + esc(p.id) + '">Chọn size ' + icon('plus') + '</a></div></div></article>';
}

function productGrid(list) { return '<div class="product-grid">' + list.map(productCard).join('') + '</div>'; }
function sectionHeader(eyebrow, title, link, label = 'Xem tất cả') {
  return '<div class="section-heading"><div><p class="eyebrow">' + eyebrow + '</p><h2>' + title + '</h2></div>' +
    (link ? '<a class="text-link" href="' + link + '">' + label + ' ' + icon('arrow') + '</a>' : '') + '</div>';
}

function shell() {
  document.querySelector('#app').innerHTML =
    '<header class="landing-header" hidden><a class="logo" href="#/" aria-label="mây. Trang chủ">mây<span>.</span></a><nav aria-label="Điều hướng giới thiệu"><button data-action="discover-landing">Chuyện của mây</button><button data-action="chat">Gặp Ami '+icon('sparkle')+'</button></nav><button id="landing-login" class="button landing-login" data-action="enter-shop">Đăng nhập '+icon('arrow')+'</button></header>' +
    '<div class="announcement"><span>Chào bạn mới! Nhập <strong>HELLOMAY</strong> để được giảm 10%</span><a href="#/vouchers">Nhận ưu đãi ' + icon('arrow') + '</a></div>' +
    '<header class="header"><div class="container header-main"><a class="logo" href="#/" aria-label="mây. Trang chủ">mây<span>.</span></a><form id="search-form" class="search-form" role="search"><label class="sr-only" for="search-input">Tìm kiếm sản phẩm</label>' + icon('search') + '<input id="search-input" name="q" placeholder="Hôm nay, bạn muốn mặc gì?" maxlength="200" autocomplete="off"><button class="icon-button voice-trigger" type="button" data-action="voice" aria-label="Tìm kiếm bằng giọng nói">' + icon('mic') + '</button><button type="submit" class="search-submit" aria-label="Tìm kiếm">' + icon('arrow') + '</button></form><div class="header-actions"><a class="header-action" href="#/favorites" aria-label="Sản phẩm yêu thích">' + icon('heart') + '<span>Yêu thích</span></a><button class="header-action" data-action="account" aria-label="Tài khoản">' + icon('user') + '<span id="account-label">Tài khoản</span></button><button class="header-action cart-trigger" data-action="cart" aria-label="Mở giỏ hàng">' + icon('bag') + '<span>Giỏ hàng</span><b id="cart-count" class="cart-count">0</b></button></div></div>' +
    '<nav class="nav container" aria-label="Điều hướng chính"><button class="category-menu-button" data-action="menu">' + icon('menu') + ' Danh mục ' + icon('down') + '</button><a href="#/" data-nav="/">Trang chủ</a><a href="#/shop" data-nav="/shop">Sản phẩm</a><a href="#/new" data-nav="/new">Hàng mới về <span class="nav-dot"></span></a><a href="#/vouchers" data-nav="/vouchers">Ưu đãi</a><a class="nav-tryon" href="#/try-on" data-nav="/try-on">' + icon('sparkle') + ' Phòng thử đồ</a><a class="nav-orders" href="#/orders">' + icon('box') + ' Đơn hàng của bạn</a><div id="category-menu" class="category-menu" hidden>' + categories.map(c => '<a href="#/shop?category=' + c.id + '">' + icon(c.icon) + esc(c.name) + icon('chevron') + '</a>').join('') + '</div></nav></header>' +
    '<main id="main" class="container" tabindex="-1"></main>' +
    '<footer class="footer"><div class="container footer-grid"><div><a class="logo" href="#/">mây<span>.</span></a><p>Những điều giản đơn.<br>Cho phong cách rất riêng của bạn.</p><span class="footer-note">Một cửa hàng thời trang demo.</span></div><div><h3>Khám phá mây.</h3><a href="#/shop">Tất cả sản phẩm</a><a href="#/try-on">Phòng thử đồ</a><a href="#/vouchers">Ưu đãi dành cho bạn</a></div><div><h3>Chúng mình ở đây</h3><button data-action="policy">Giao hàng & đổi trả</button><button data-action="chat">Trò chuyện với Ami</button><a href="#/orders">Theo dõi đơn hàng</a></div><div class="footer-promise"><span>' + icon('heart') + '</span><h3>Mặc đẹp, theo cách của bạn.</h3><p>Một chút thoải mái.<br>Một chút tự tin. Một chút mây.</p></div></div><div class="container footer-bottom"><span>© 2026 mây. · Bản demo học tập</span><span>Tên, giá & ảnh có nguồn từ nhà bán lẻ · Đơn hàng chỉ dùng trong demo</span><a href="#/admin">Quản trị</a></div></footer>' +
    '<button class="chat-launcher" data-action="chat" aria-label="Mở trợ lý tư vấn">' + icon('chat') + '<span>Hỏi mây nhé!</span><b></b></button><aside id="chat-panel" class="chat-panel" aria-labelledby="chat-title" hidden><div class="chat-header"><span class="chat-avatar">' + icon('sparkle') + '</span><div><h2 id="chat-title">Ami · mây.</h2><p>Trợ lý thời trang · Có giọng nói</p></div><button class="icon-button" data-action="chat" aria-label="Đóng trò chuyện">' + icon('close') + '</button></div><div id="ami-stage" class="ami-stage"><iframe id="ami-avatar" title="Nhân vật Live2D Ami" data-src="/ami-assets/may-avatar.html"></iframe><div class="ami-intro"><span class="eyebrow">GẶP AMI</span><strong>Gu của bạn,<br>mình cùng tìm.</strong><p id="ami-status">Ami đang chuẩn bị…</p></div></div><div class="chat-voice-tools"><label><input id="auto-read" type="checkbox"> Tự đọc câu trả lời</label><button data-action="stop-speaking" class="small-link">Dừng giọng nói</button></div><p id="chat-status" class="chat-status" role="status"></p><div id="chat-log" class="chat-log" aria-live="polite"></div><div class="chat-suggestions"><button data-action="chat-prompt" data-prompt="Tư vấn áo len">Tìm áo len</button><button data-action="chat-prompt" data-prompt="Có voucher nào?">Mã giảm giá</button></div><form id="chat-form" class="chat-form"><label class="sr-only" for="chat-input">Câu hỏi cho trợ lý</label><input id="chat-input" name="content" placeholder="Hỏi Ami về món đồ bạn thích…" maxlength="2000" required><button type="button" class="icon-button" data-action="chat-voice" aria-label="Nói với Ami">' + icon('mic') + '</button><button type="submit" class="icon-button" aria-label="Gửi câu hỏi">' + icon('send') + '</button></form><button class="clear-chat" data-action="clear-chat">Xóa lịch sử trò chuyện</button></aside>';
}

function updateHeader() {
  document.querySelector('#cart-count').textContent = String(cart.reduce((n, line) => n + line.quantity, 0));
  document.querySelector('#account-label').textContent = customer?.registered ? customer.full_name.split(' ').at(-1) : 'Tài khoản';
}

function homePage() {
  const featured = products.slice(0, 4);
  const discount = products.filter(p => p.original_price > p.price);
  const homeCategories = categories.filter(c => products.some(p => p.category === c.id));
  return '<section class="hero-grid"><div class="hero-main"><img class="hero-image" src="/static/assets/collection.png" alt="Bộ sưu tập thời trang với áo sơ mi tím và quần ống rộng" width="1536" height="1024"><div class="hero-copy"><span class="collection-label"><span></span> THE EVERYDAY EDIT</span><h1>Mặc điều<br>bạn <em>thích.</em></h1><p>Nhẹ nhàng một chút. Tự tin thêm nhiều.<br>Tìm những món đồ dành riêng cho bạn.</p><a class="button dark" href="#/shop">Khám phá bộ sưu tập ' + icon('arrow') + '</a></div><div class="hero-footnote">THOẢI MÁI MỖI NGÀY · PHONG CÁCH RIÊNG BẠN</div></div>' +
    '<div class="hero-side"><div class="try-promo"><span class="pill">' + icon('sparkle') + ' MỘT CÁCH MUA SẮM MỚI</span><h2>Hợp gu?<br>Thử là biết.</h2><p>Phối thử món đồ yêu thích<br>trực tiếp qua camera.</p><a class="text-link" href="#/try-on">Vào phòng thử đồ ' + icon('arrow') + '</a><div class="try-promo-art"><img src="/static/assets/glasses.svg" alt="" width="200" height="200"><span>' + icon('sparkle') + '</span><img src="/static/assets/watch.svg" alt="" width="180" height="180"></div><span class="demo-pill">Camera realtime · Demo</span></div><a class="voucher-promo" href="#/vouchers"><span class="voucher-icon">' + icon('ticket') + '</span><div><small>QUÀ CHÀO BẠN MỚI</small><strong>Giảm 10% đơn đầu</strong><span>Nhập mã HELLOMAY</span></div>' + icon('arrow') + '</a></div></section>' +
    '<div class="benefit-bar"><div>' + icon('truck') + '<span><strong>Giao hàng miễn phí</strong><small>Cho đơn từ 499.000₫</small></span></div><div>' + icon('refresh') + '<span><strong>Đổi trả dễ dàng</strong><small>Trong vòng 7 ngày</small></span></div><div>' + icon('shield') + '<span><strong>Mua sắm an tâm</strong><small>Thông tin luôn rõ ràng</small></span></div><div>' + icon('sparkle') + '<span><strong>Thử trước, chọn sau</strong><small>Phối đồ ngay trên ảnh</small></span></div></div>' +
    '<section class="category-section">' + sectionHeader('TỦ ĐỒ CỦA BẠN', 'Hôm nay mặc gì?', '#/shop') + '<div class="category-grid">' + homeCategories.map(c => '<a class="category-card" href="#/shop?category=' + c.id + '"><span>' + icon(c.icon) + '</span><strong>' + esc(c.name) + '</strong><small>' + products.filter(p => p.category === c.id).length + ' lựa chọn</small></a>').join('') + '</div></section>' +
    '<section class="featured-section">' + sectionHeader('CHỌN MỘT CHÚT MỚI MẺ', 'Ghé mây, gặp đồ xinh.', '#/shop') + '<div class="section-tabs"><a class="active" href="#/shop">Dành cho bạn</a><a href="#/shop?category=tops">Áo xinh</a><a href="#/shop?category=bottoms">Quần đẹp</a><a href="#/shop?category=outerwear">Áo khoác</a><a href="#/shop?try_on=true">Có thể thử phối ' + icon('sparkle') + '</a></div>' + productGrid(featured) + '</section>' +
    '<section class="style-banner"><div><p class="eyebrow">PHÒNG THỬ ĐỒ CỦA RIÊNG BẠN</p><h2>Thêm chút hình dung.<br>Chọn đồ thêm tự tin.</h2><p>Bật camera, chọn món đồ, thử một phong cách mới.<br>Camera chỉ xử lý trên thiết bị của bạn.</p><a class="button primary" href="#/try-on">Thử phối đồ ngay ' + icon('sparkle') + '</a></div><div class="style-banner-art"><img src="/static/assets/shirt.svg" alt="Minh họa áo sơ mi tím" width="300" height="300"><div class="floating-tag">' + icon('check') + ' Hợp với bạn đó!</div><div class="outline-flower">✳</div></div></section>' +
    '<section>' + sectionHeader(discount.length ? 'MUA VUI HƠN MỘT CHÚT' : 'THÊM VÀO TỦ ĐỒ', discount.length ? 'Món xinh, giá cũng xinh.' : 'Những lựa chọn tiếp theo', '#/shop?sort=price-asc') + productGrid((discount.length ? discount : products.slice(4)).slice(0, 4)) + '</section>' +
    '<section class="brand-note"><span class="little-flower">✳</span><p>Không cần giống ai.<br><strong>Chỉ cần thật là bạn.</strong></p><a href="#/shop">Tìm phong cách của bạn ' + icon('arrow') + '</a></section>';
}

async function shopPage(params, path) {
  const favoriteOnly = path === '/favorites';
  const newArrivals = path === '/new';
  const categoryPath = newArrivals ? '#/new' : '#/shop';
  const q = params.get('q') || '';
  const cat = params.get('category') || '';
  const sort = params.get('sort') || (newArrivals ? 'new' : 'popular');
  let list = products.filter(p => (!favoriteOnly || saved.has(p.id)) && (!cat || p.category === cat) && (!params.get('try_on') || p.try_on));
  let searchNote='';
  if(q){
    const result=await api('/search',json('POST',{query:q,category:cat}));
    const ranked=new Map(result.product_ids.map((id,index)=>[id,index]));
    list=list.filter(p=>ranked.has(p.id)).sort((a,b)=>ranked.get(a.id)-ranked.get(b.id));
    if(result.fallback_reason)searchNote='<p class="search-service-note">Đang tìm theo từ khóa. Tìm kiếm ngữ nghĩa tạm chưa sẵn sàng.</p>';
  }
  if (sort === 'new') list.sort((a,b) => (b.collected_at||'').localeCompare(a.collected_at||'') || products.indexOf(b)-products.indexOf(a));
  if (sort === 'price-asc') list.sort((a,b) => a.price-b.price);
  if (sort === 'price-desc') list.sort((a,b) => b.price-a.price);
  const title = favoriteOnly ? 'Tủ đồ yêu thích' : q ? 'Kết quả cho “' + esc(q) + '”' : newArrivals ? 'Hàng mới về' : categories.find(c => c.id === cat)?.name || 'Tìm điều bạn thích.';
  return searchNote+'<div class="page-intro"><p class="eyebrow">MỘT CHÚT MÂY, MỖI NGÀY</p><h1>' + title + '</h1><p>' + (favoriteOnly ? 'Những món đồ bạn muốn dành thêm một chút thương.' : newArrivals ? 'Những sản phẩm mới được thêm vào danh mục của mây.' : 'Chọn món đồ vừa vặn với phong cách của bạn.') + '</p></div>' +
    '<div class="order-tools"><button type="button" class="button secondary" data-report="image-search">Tìm bằng ảnh</button><a class="button secondary" href="#/recommendations">Gợi ý cho bạn</a></div><div class="shop-toolbar"><div class="filter-chips"><a class="chip ' + (!cat?'active':'') + '" href="'+categoryPath+'">Tất cả</a>' + categories.filter(c => products.some(p=>p.category===c.id)).map(c => '<a class="chip ' + (cat===c.id?'active':'') + '" href="' + categoryPath + '?category=' + c.id + '">' + esc(c.name) + '</a>').join('') + '</div><label class="sort-label"><span>Sắp xếp</span><select id="sort-products"><option value="new" ' + (sort==='new'?'selected':'') + '>Mới thêm</option><option value="popular" ' + (sort==='popular'?'selected':'') + '>Đề xuất</option><option value="price-asc" ' + (sort==='price-asc'?'selected':'') + '>Giá tăng dần</option><option value="price-desc" ' + (sort==='price-desc'?'selected':'') + '>Giá giảm dần</option></select></label></div><p class="result-count">' + list.length + ' sản phẩm' + (q ? ' · <a href="#/shop">Xóa tìm kiếm</a>' : '') + '</p>' +
    (list.length ? productGrid(list) : emptyState(favoriteOnly?'heart':'search', favoriteOnly?'Chưa có món đồ yêu thích':'Chưa tìm thấy món đồ phù hợp', favoriteOnly?'Nhấn trái tim trên sản phẩm để lưu vào đây.':'Thử từ khóa ngắn hơn, như “áo len”, hoặc khám phá danh mục khác.')) +
    '<p class="source-note">Sản phẩm có nguồn được lưu tại thời điểm thu thập. Xem trang chi tiết để kiểm tra nguồn, giá và các thuộc tính mô phỏng.</p>';
}

function detailPage(p) {
  selectedProduct = p;
  const sizes = [...new Set(p.variants.map(v => v.size))];
  const colors = [...new Set(p.variants.map(v => v.color))];
  return '<div class="breadcrumb"><a href="#/">Trang chủ</a>' + icon('chevron') + '<a href="#/shop?category=' + p.category + '">' + esc(categories.find(c => c.id===p.category)?.name || 'Sản phẩm') + '</a>' + icon('chevron') + '<span>' + esc(p.name) + '</span></div><section class="product-detail"><div class="detail-photo"><img src="' + imagePath(p.image) + '" alt="' + esc(p.name) + '" width="600" height="750"><button class="favorite-button" data-action="favorite" data-id="' + p.id + '" aria-label="Yêu thích sản phẩm" aria-pressed="' + saved.has(p.id) + '">' + icon('heart') + '</button></div><div class="detail-content"><p class="eyebrow">' + esc(p.brand) + '</p><h1>' + esc(p.name) + '</h1>' +
    '<p class="detail-meta">' + (p.rating ? icon('star') + ' ' + p.rating + ' · ' : '') + 'Mã sản phẩm: ' + esc(p.id) + '</p><div class="detail-price"><strong>' + money(p.price) + '</strong>' + (p.original_price>p.price?'<del>'+money(p.original_price)+'</del>':'') + '</div><p class="detail-description">Một lựa chọn cho những ngày bạn muốn mặc thật thoải mái và tự tin theo cách của mình.</p><form id="add-product-form"><fieldset><legend>Màu sắc</legend><div class="option-row">' +
    colors.map((color,i)=>'<label class="option"><input type="radio" name="color" value="' + esc(color) + '" '+(!i?'checked':'')+'><span>' + esc(color) + '</span></label>').join('') + '</div></fieldset><fieldset><legend>Kích cỡ <button type="button" class="small-link" data-action="size-guide">Hướng dẫn chọn size</button></legend><div class="option-row">' +
    sizes.map((size,i)=>'<label class="option"><input type="radio" name="size" value="'+esc(size)+'" '+(!i?'checked':'')+'><span>'+esc(size)+'</span></label>').join('') + '</div></fieldset><div class="quantity-section"><label for="product-quantity">Số lượng</label><div class="quantity-control"><button type="button" data-action="detail-minus" aria-label="Giảm số lượng">'+icon('minus')+'</button><input id="product-quantity" name="quantity" type="number" value="1" min="1" max="99" required><button type="button" data-action="detail-plus" aria-label="Tăng số lượng">'+icon('plus')+'</button></div><span id="variant-stock" class="muted">'+p.variants[0].stock+' sản phẩm có sẵn</span></div><p id="product-error" class="form-error" role="alert"></p><div class="detail-actions"><button class="button primary" type="submit">'+icon('bag')+' Thêm vào giỏ hàng</button><button class="button secondary" type="submit" name="buyNow" value="true">Mua ngay</button></div></form>' +
    (p.try_on ? '<a class="try-on-link" href="#/try-on?product='+p.id+'">'+icon('sparkle')+' Thử phối món đồ này qua camera '+icon('arrow')+'</a>' : '') +
    '<div class="detail-promises"><span>'+icon('truck')+' Miễn phí giao từ 499K</span><span>'+icon('refresh')+' Đổi trả trong 7 ngày</span></div><details open class="product-details"><summary>Thông tin sản phẩm</summary><dl>'+Object.entries(p.specs).map(([key,value])=>'<div><dt>'+esc(key)+'</dt><dd>'+esc(value)+'</dd></div>').join('')+'</dl></details>' +
    (p.source_url ? '<div class="source-box">'+icon('info')+'<div><strong>Nguồn dữ liệu sản phẩm</strong><a href="'+esc(p.source_url)+'" target="_blank" rel="noopener noreferrer">Xem sản phẩm tại '+esc(p.brand)+' ↗</a><small>Ghi nhận '+esc(p.collected_at||'04/11/2026')+'. Tồn kho và đơn hàng được mô phỏng riêng.</small></div></div>' : '<p class="source-note">Sản phẩm mẫu dành cho trải nghiệm đeo thử; hình ảnh và giá chỉ minh họa.</p>') +
    '</div></section><section>'+sectionHeader('GỢI Ý THÊM CHO BẠN','Một chút hợp gu.','#/shop')+productGrid(products.filter(item=>item.id!==p.id).slice(0,4))+'</section>';
}

function cartRows() {
  return cart.map(line => '<div class="cart-line"><a href="#/product/'+esc(line.product_id)+'"><img src="'+imagePath(line.image)+'" alt="'+esc(line.name)+'" width="88" height="108"></a><div class="cart-line-info"><a href="#/product/'+esc(line.product_id)+'">'+esc(line.name)+'</a><small>'+esc(line.color)+' / '+esc(line.size)+'</small><strong>'+money(line.price)+'</strong><div class="cart-line-actions"><div class="quantity-control small"><button data-action="cart-minus" data-id="'+esc(line.variant_id)+'" aria-label="Giảm số lượng" '+(line.quantity<=1?'disabled':'')+'>'+icon('minus')+'</button><span>'+line.quantity+'</span><button data-action="cart-plus" data-id="'+esc(line.variant_id)+'" aria-label="Tăng số lượng">'+icon('plus')+'</button></div><button class="icon-button muted" data-action="cart-remove" data-id="'+esc(line.variant_id)+'" aria-label="Xóa '+esc(line.name)+'">'+icon('trash')+'</button></div></div></div>').join('');
}

function openCart() {
  modal.className = 'cart-drawer';
  modal.innerHTML = '<div class="dialog-top"><h2 id="dialog-title">Giỏ đồ của bạn <span>('+cart.reduce((n,l)=>n+l.quantity,0)+')</span></h2><button class="icon-button" data-action="close-modal" aria-label="Đóng">'+icon('close')+'</button></div>' +
    (cart.length ? '<div class="cart-scroll">'+cartRows()+'</div><div class="cart-summary"><div><span>Tạm tính</span><strong>'+money(cart.reduce((n,l)=>n+l.price*l.quantity,0))+'</strong></div><p>'+icon('ticket')+' Thêm mã ưu đãi ở bước thanh toán</p><a href="#/checkout" class="button primary full">Tiến hành đặt hàng '+icon('arrow')+'</a><button class="button ghost full" data-action="close-modal">Tiếp tục chọn đồ</button></div>' : emptyState('bag','Giỏ đồ còn đang trống','Một món đồ xinh đang đợi bạn đấy.'));
  if (!modal.open) modal.showModal();
}

function quoteMarkup(quote) {
  return '<div class="summary-line"><span>Tạm tính</span><span>'+money(quote.subtotal)+'</span></div><div class="summary-line"><span>Giảm giá</span><span class="purple">−'+money(quote.discount)+'</span></div><div class="summary-line"><span>Giao hàng</span><span>'+ (quote.shipping?money(quote.shipping):'Miễn phí') +'</span></div><div class="summary-total"><span>Tổng cộng</span><strong>'+money(quote.total)+'</strong></div>';
}

function checkoutProducts() {
  return cart.map(l=>'<div class="checkout-product"><img src="'+imagePath(l.image)+'" alt="" width="56" height="70"><div><strong>'+esc(l.name)+'</strong><small>'+esc(l.color)+' / '+esc(l.size)+' · SL '+l.quantity+'</small></div><span>'+money(l.price*l.quantity)+'</span></div>').join('');
}

async function checkoutPage() {
  cart = await api('/cart');
  if (!cart.length) return emptyState('bag','Bạn chưa chọn món đồ nào','Thêm một sản phẩm vào giỏ để bắt đầu đặt hàng.');
  checkoutQuote = await api('/checkout/quote',json('POST',{voucher:''}));
  checkoutKey = crypto.randomUUID();
  return '<div class="page-intro"><p class="eyebrow">SẮP ĐẾN TỦ ĐỒ CỦA BẠN</p><h1>Hoàn tất đơn hàng.</h1><p>Thêm một chút thông tin để mây gửi đồ đến bạn.</p></div><form id="checkout-form" class="checkout-layout"><div><section class="surface"><h2><span class="step-badge">1</span> Thông tin nhận hàng</h2><div class="form-grid"><label class="field">Họ và tên<input name="recipient_name" autocomplete="name" minlength="2" maxlength="100" value="'+esc(customer.registered?customer.full_name:'')+'" placeholder="Tên người nhận" required></label><label class="field">Số điện thoại<input name="phone" type="tel" autocomplete="tel" pattern="0[35789][0-9]{8}" placeholder="09xxxxxxxx" required><small>Số điện thoại Việt Nam gồm 10 chữ số</small></label><label class="field span-2">Địa chỉ giao hàng<textarea name="address" autocomplete="street-address" minlength="10" maxlength="500" placeholder="Số nhà, đường, phường/xã, tỉnh/thành phố" required></textarea></label></div></section><section class="surface"><h2><span class="step-badge">2</span> Phương thức thanh toán</h2><label class="payment-option"><input name="payment_method" type="radio" value="cod" checked><span>'+icon('box')+'</span><div><strong>Thanh toán khi nhận hàng</strong><small>COD · Thanh toán cho người giao hàng</small></div></label><label class="payment-option"><input name="payment_method" type="radio" value="online-demo"><span>'+icon('shield')+'</span><div><strong>Thanh toán trực tuyến · Demo</strong><small>Mô phỏng thành công, thất bại hoặc hủy. Không thu tiền thật.</small></div></label></section></div><aside class="surface order-summary"><h2>Đơn hàng của bạn</h2>'+'<div id="checkout-products">'+checkoutProducts()+'</div>'+'<label class="field voucher-field">Mã ưu đãi<div><input id="voucher-code" name="voucher" maxlength="40" placeholder="Ví dụ: HELLOMAY"><button class="button secondary" type="button" data-action="apply-voucher">Áp dụng</button></div></label><p id="voucher-message" class="form-error" role="status"></p><div id="quote-summary">'+quoteMarkup(checkoutQuote)+'</div><p id="checkout-error" class="form-error" role="alert"></p><button class="button primary full" type="submit" id="place-order">Xác nhận đặt hàng '+icon('arrow')+'</button><p class="fine-print">'+icon('lock')+' Đơn hàng demo được lưu trên máy chủ cục bộ.</p></aside></form>';
}

async function ordersPage() {
  const orders = await api('/orders');
  return '<div class="page-intro"><p class="eyebrow">HÀNH TRÌNH ĐẾN VỚI BẠN</p><h1>Đơn hàng của bạn.</h1><p>Theo dõi những món đồ bạn đã chọn.</p></div>' + (orders.length ? '<div class="orders-list">'+orders.map(o=>'<article class="surface order-card" id="order-'+o.id+'"><div class="order-heading"><div><strong>'+esc(o.id)+'</strong><span>'+esc(o.created_at)+' UTC</span></div><span class="status-pill">'+esc(statusNames[o.status]||o.status)+'</span></div>'+o.items.map(l=>'<div class="order-product"><img src="'+imagePath(l.image)+'" alt="" width="64" height="80"><div><strong>'+esc(l.name)+'</strong><small>'+esc(l.color)+' / '+esc(l.size)+' · SL '+l.quantity+'</small></div><span>'+money(l.unit_price*l.quantity)+'</span></div>').join('')+'<div class="order-end"><div><span>'+esc(o.payment_method==='cod'?'Thanh toán khi nhận hàng':'Trực tuyến mô phỏng')+'</span><small>'+esc(paymentNames[o.payment_status]||o.payment_status)+'</small></div><strong>'+money(o.total)+'</strong>'+(o.payment_method==='online-demo'&&o.status==='pending_payment'?button('Tiếp tục thanh toán','pay-order','primary','data-id="'+o.id+'"'):'')+'</div><details><summary>Thông tin giao hàng & chi phí</summary><p>'+esc(o.recipient_name)+' · '+esc(o.phone)+'<br>'+esc(o.address)+'</p>'+quoteMarkup(o)+'</details>'+orderExtras(o)+'</article>').join('')+'</div>' : emptyState('box','Chưa có đơn hàng nào','Món đồ đầu tiên sẽ xuất hiện tại đây sau khi bạn đặt hàng.'));
}

async function vouchersPage() {
  const vouchers = await api('/vouchers');
  return '<div class="page-intro"><p class="eyebrow">MỘT CHÚT QUÀ TỪ MÂY</p><h1>Mua vui hơn một chút.</h1><p>Lưu mã bạn thích, áp dụng khi đặt hàng. Mỗi đơn sử dụng một mã.</p></div><div class="voucher-grid">'+vouchers.map(v=>'<article class="voucher-card"><span class="voucher-emblem">'+icon('ticket')+'</span><div><p class="eyebrow">ƯU ĐÃI TẠI MÂY</p><h2>'+esc(v.title)+'</h2><p>Đơn tối thiểu '+money(v.minimum)+(v.kind==='percent'?' · Giảm tối đa '+money(v.maximum):'')+'</p><div class="voucher-code"><code>'+esc(v.code)+'</code>'+button('Sao chép','copy-voucher','secondary','data-code="'+v.code+'"')+'</div><small>Voucher demo của mây, không áp dụng tại website nguồn.</small></div></article>').join('')+'</div>';
}

async function renderRoute() {
  const version = ++routeVersion;
  cleanupTryOn?.();
  cleanupTryOn = null;
  if (modal.open) modal.close();
  document.querySelector('#category-menu').hidden = true;
  let [path, query] = (location.hash.slice(1)||'/').split('?');
  if (path === '/shop' && new URLSearchParams(query).get('sort') === 'new') {
    path = '/new';
    history.replaceState(null, '', '#/new?' + query);
  }
  const needsLogin = !customer.registered && isShoppingRoute(path);
  if (needsLogin) {
    authDestination = path + (query ? '?' + query : '');
    history.replaceState(null, '', '#/');
    path = '/';
    query = '';
  }
  const isLanding = path === '/' && !customer.registered;
  document.body.classList.toggle('landing-mode', isLanding);
  document.querySelector('.landing-header').hidden = !isLanding;
  const params = new URLSearchParams(query);
  const main = document.querySelector('#main');
  main.innerHTML = '<div class="page-loading"><span class="spinner"></span> Mây đang chuẩn bị một chút…</div>';
  document.querySelectorAll('[data-nav]').forEach(a=>a.classList.toggle('active',a.dataset.nav===path));
  document.querySelector('#search-input').value = params.get('q') || '';
  try {
    let html;
    if (path === '/') html = isLanding ? landingPage(products) : homePage();
    else if (path === '/shop' || path === '/favorites' || path === '/new') html = await shopPage(params,path);
    else if (path.startsWith('/product/')) html = detailPage(await api('/products/'+encodeURIComponent(path.split('/')[2])));
    else if (path === '/checkout') html = await checkoutPage();
    else if (path === '/orders') html = await ordersPage();
    else if (path === '/vouchers') html = await vouchersPage();
    else if (path === '/admin') html = await reportUI.staffPage();
    else if (path === '/recommendations') html = await reportUI.recommendationsPage();
    else if (path === '/addresses') html = await reportUI.addressesPage();
    else if (path === '/try-on') {
      if (version!==routeVersion) return;
      main.innerHTML = '';
      cleanupTryOn = await mountTryOn(main, products, params.get('product'), toast);
      window.scrollTo(0,0);
      return;
    } else html = emptyState('search','Trang này chưa có ở mây.','Bạn có thể trở lại cửa hàng để tiếp tục khám phá.');
    if (version !== routeVersion) return;
    main.innerHTML = html;
    updateHeader();
    window.scrollTo(0,0);
    document.title = (path==='/'?'Mặc điều bạn thích.':path==='/try-on'?'Phòng thử đồ':main.querySelector('h1')?.textContent||'Cửa hàng thời trang')+' | mây.';
    if (needsLogin) openAccount();
    if (path === '/orders' && pendingPaymentId) {
      const id = pendingPaymentId;
      pendingPaymentId = null;
      openPayment(id);
    }
  } catch(err) {
    if (version === routeVersion) main.innerHTML = emptyState('info','Chưa mở được nội dung.',esc(err.message),button('Thử lại','retry','primary'));
  }
}

function isShoppingRoute(path) {
  return ['/admin', '/addresses'].includes(path);
}

function openAccount(register = false) {
  modal.className = 'account-modal';
  if (customer.registered) {
    modal.innerHTML = '<div class="dialog-top"><h2 id="dialog-title">Chào '+esc(customer.full_name)+'</h2><button class="icon-button" data-action="close-modal" aria-label="Đóng">'+icon('close')+'</button></div><p class="muted">'+esc(customer.email)+'</p><a class="button secondary full" href="#/orders">Đơn hàng của bạn '+icon('box')+'</a>'+(['merchant','support','operator'].includes(customer.role)?'<a class="button secondary full" href="#/admin">Quản trị cửa hàng</a>':'')+'<a class="button secondary full" href="#/recommendations">Gợi ý và quyền riêng tư</a><a class="button secondary full" href="#/addresses">Địa chỉ của bạn</a>'+button('Đăng xuất','logout','ghost full');
  } else {
    modal.innerHTML = '<div class="dialog-top"><h2 id="dialog-title">'+(register?'Thành viên mới của mây.':'Chào bạn, mây đây.')+'</h2><button class="icon-button" data-action="close-modal" aria-label="Đóng">'+icon('close')+'</button></div><p class="muted">'+(register?'Tạo tài khoản để lưu những món đồ và đơn hàng của bạn.':'Đăng nhập để tiếp tục hành trình phong cách của bạn.')+'</p><form id="auth-form" data-mode="'+(register?'register':'login')+'">'+(register?'<label class="field">Tên của bạn<input name="full_name" autocomplete="name" minlength="2" maxlength="100" required></label>':'')+'<label class="field">Email<input name="email" type="email" autocomplete="email" maxlength="254" required></label><label class="field">Mật khẩu<input name="password" type="password" autocomplete="'+(register?'new-password':'current-password')+'" minlength="8" maxlength="128" required><small>Ít nhất 8 ký tự</small></label><p id="auth-error" class="form-error" role="alert"></p><button class="button primary full" type="submit">'+(register?'Tạo tài khoản':'Đăng nhập')+'</button></form><p class="center muted">'+(register?'Đã có tài khoản? ':'Chưa có tài khoản? ')+button(register?'Đăng nhập':'Đăng ký','auth-toggle','text-button','data-register="'+(!register)+'"')+'</p>';
  }
  if (!modal.open) modal.showModal();
}

function openInfo(title, body) {
  modal.className = 'info-modal';
  modal.innerHTML = '<div class="dialog-top"><h2 id="dialog-title">'+title+'</h2><button class="icon-button" data-action="close-modal" aria-label="Đóng">'+icon('close')+'</button></div>'+body;
  modal.showModal();
}

function openPayment(id) {
  openInfo('Thanh toán trực tuyến · Demo','<p>Đơn <strong>'+esc(id)+'</strong> đã được tạo. Chọn một kết quả để thử luồng thanh toán. Thao tác này không thu tiền thật.</p><div class="payment-demo-buttons">'+button('Mô phỏng thành công','payment-outcome','primary full','data-id="'+id+'" data-outcome="success"')+button('Mô phỏng thất bại','payment-outcome','secondary full','data-id="'+id+'" data-outcome="failure"')+button('Dừng thanh toán','payment-outcome','ghost full','data-id="'+id+'" data-outcome="cancel"')+'</div><p id="payment-error" class="form-error" role="alert"></p>');
}

async function refreshCart() { cart=await api('/cart'); updateHeader(); }
async function refreshCustomer() {
  chatGeneration++;chatRequest?.abort();chatRequest=null;chatBusy=false;amiVoice.clear();
  customer=await api('/me');
  await refreshCart();
  document.querySelector('#chat-log')?.replaceChildren();
  const sendButton=document.querySelector('#chat-form [type="submit"]');
  if(sendButton)sendButton.disabled=false;
}

function appendChat(sender, text, ids = [], messageId = null) {
  const log=document.querySelector('#chat-log');
  const element=document.createElement('div');
  element.className='chat-message '+sender;
  element.innerHTML='<p>'+esc(text)+'</p>'+ids.map(id=>{const p=products.find(p=>p.id===id);return p?'<a class="chat-product" href="#/product/'+esc(id)+'"><img src="'+imagePath(p.image)+'" alt="" width="40" height="50"><span>'+esc(p.name)+'<strong>'+money(p.price)+'</strong></span>'+icon('arrow')+'</a>':'';}).join('');
  if(sender==='assistant'&&messageId)element.innerHTML+='<button class="listen-reply" data-action="speak-message" data-id="'+messageId+'">'+icon('mic')+' Nghe Ami</button>';
  log.append(element);
  log.scrollTop=log.scrollHeight;
}

async function sendChat(content) {
  if(chatBusy||!content.trim()) return;
  chatBusy=true;
  const generation=chatGeneration;
  chatRequest=new AbortController();
  amiVoice.stop();
  amiExpression('Think_1');
  appendChat('user',content);
  const form=document.querySelector('#chat-form');
  form.querySelector('[type="submit"]').disabled=true;
  form.querySelector('input').value='';
  document.querySelector('#chat-status').textContent='Ami đang xem dữ liệu cửa hàng và suy nghĩ…';
  let reply;
  try {
    reply=await api('/chat',{...json('POST',{content}),signal:chatRequest.signal});
    if(generation!==chatGeneration)return;
    appendChat('assistant',reply.content,reply.product_ids,reply.message_id);
    amiExpression('Happy');
  } catch(err){
    if(err.name!=='AbortError'&&generation===chatGeneration)appendChat('assistant','Chưa gửi được câu hỏi: '+err.message);
  } finally {
    if(generation===chatGeneration){
      chatBusy=false;chatRequest=null;form.querySelector('[type="submit"]').disabled=false;
      document.querySelector('#chat-status').textContent='';
    }
  }
  if(reply&&autoRead&&generation===chatGeneration){
    try{await amiVoice.speak(reply.message_id);}catch(err){toast(err.message);}
  }
}

document.addEventListener('click',async event=>{
  const target=event.target.closest('[data-action]');
  if(!target) {
    if(event.target.closest('a[href^="#/"]')&&modal.open) modal.close();
    return;
  }
  const { action,id }=target.dataset;
  if(target.disabled) return;
  try {
    if(action==='close-modal') modal.close();
    else if(action==='landing-music') toggleLandingMusic();
    else if(action==='enter-shop') navigate('/shop');
    else if(action==='landing-register') {authDestination='/shop';openAccount(true);}
    else if(action==='discover-landing') document.querySelector('#landing-discover').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
    else if(action==='retry') renderRoute();
    else if(action==='menu') document.querySelector('#category-menu').hidden=!document.querySelector('#category-menu').hidden;
    else if(action==='voice') { if(modal.open)modal.close(); openVoice(modal,text=>navigate('/shop?q='+encodeURIComponent(text)), {title:'Tìm bằng giọng nói',description:'Nói tên món đồ bạn đang tìm, ví dụ: áo len nữ.',submitLabel:'Tìm sản phẩm'}); }
    else if(action==='chat-voice') { if(modal.open)modal.close(); openVoice(modal,text=>sendChat(text),{title:'Nói với Ami',description:'Ghi âm câu hỏi, kiểm tra bản chép rồi gửi cho Ami.',submitLabel:'Gửi cho Ami'}); }
    else if(action==='speak-message') {await amiVoice.speak(Number(id));}
    else if(action==='stop-speaking') amiVoice.stop();
    else if(action==='cart') {
      await refreshCart();openCart();
    }
    else if(action==='favorite') {
      if(saved.has(id))saved.delete(id);else saved.add(id);
      localStorage.setItem('may:saved',JSON.stringify([...saved]));
      document.querySelectorAll('[data-action="favorite"][data-id="'+CSS.escape(id)+'"]').forEach(el=>{el.classList.toggle('is-saved',saved.has(id));el.setAttribute('aria-pressed',String(saved.has(id)));});
      toast(saved.has(id)?'Đã thêm vào tủ đồ yêu thích':'Đã bỏ khỏi tủ đồ yêu thích');
      if(location.hash.startsWith('#/favorites')) renderRoute();
    } else if(action==='account') openAccount();
    else if(action==='auth-toggle') openAccount(target.dataset.register==='true');
    else if(action==='logout') {await api('/auth/logout',json('POST',{}));await refreshCustomer();modal.close();navigate('/');toast('Đã đăng xuất');}
    else if(action.startsWith('cart-')) {
      const line=cart.find(l=>l.variant_id===id);
      target.disabled=true;
      cart=action==='cart-remove'?await api('/cart/'+encodeURIComponent(id),{method:'DELETE'}):await api('/cart/'+encodeURIComponent(id),json('PUT',{variant_id:id,quantity:line.quantity+(action==='cart-plus'?1:-1)}));
      updateHeader();openCart();
    } else if(action==='detail-minus'||action==='detail-plus') {
      const input=document.querySelector('#product-quantity');
      input.value=String(Math.min(99,Math.max(1,Number(input.value)+(action==='detail-plus'?1:-1))));
    } else if(action==='apply-voucher') {
      const input=document.querySelector('#voucher-code');
      const message=document.querySelector('#voucher-message');
      target.disabled=true;
      try {
        checkoutQuote=await api('/checkout/quote',json('POST',{voucher:input.value.trim()}));
        input.value=checkoutQuote.voucher||'';
        document.querySelector('#quote-summary').innerHTML=quoteMarkup(checkoutQuote);
        message.textContent=checkoutQuote.voucher?'Đã áp dụng '+checkoutQuote.voucher:'Đã bỏ mã ưu đãi';
        message.className='success-text';
      } catch(err){message.textContent=err.message;message.className='form-error';}
      finally{target.disabled=false;}
    } else if(action==='copy-voucher') {
      await navigator.clipboard.writeText(target.dataset.code);toast('Đã sao chép mã '+target.dataset.code);
    } else if(action==='pay-order') openPayment(id);
    else if(action==='payment-outcome') {
      target.disabled=true;
      const order=await api('/orders/'+id+'/demo-payment',json('POST',{outcome:target.dataset.outcome}));
      modal.close();await renderRoute();toast(paymentNames[order.payment_status]);
    } else if(action==='policy') openInfo('Mua sắm cùng mây.','<div class="policy-content"><h3>Giao hàng</h3><p>Phí giao hàng demo 30.000₫. Miễn phí cho đơn từ 499.000₫. Thời gian dự kiến 2–4 ngày làm việc.</p><h3>Đổi trả</h3><p>Chính sách demo: đổi trả trong 7 ngày khi sản phẩm còn nhãn và chưa sử dụng.</p><h3>Dữ liệu & quyền riêng tư</h3><p>Ảnh và video thử đồ chỉ xử lý trong trình duyệt. Giọng nói được gửi tới ElevenLabs sau khi bạn yêu cầu chuyển thành văn bản. Đơn hàng, tồn kho, voucher và tư vấn là dữ liệu của bản demo, độc lập với nhà bán lẻ nguồn.</p></div>');
    else if(action==='size-guide') openInfo('Chọn size vừa vặn.','<p>Bảng tham khảo demo cho quần áo. Size thực tế tùy sản phẩm; đối chiếu hướng dẫn ở liên kết nguồn.</p><table><thead><tr><th>Size</th><th>Ngực (cm)</th><th>Eo (cm)</th><th>Hông (cm)</th></tr></thead><tbody><tr><td>S</td><td>82–86</td><td>64–68</td><td>88–92</td></tr><tr><td>M</td><td>86–90</td><td>68–72</td><td>92–96</td></tr><tr><td>L</td><td>90–94</td><td>72–76</td><td>96–100</td></tr><tr><td>XL</td><td>94–98</td><td>76–80</td><td>100–104</td></tr></tbody></table><p class="fine-print">Thử phối bằng ảnh không xác định kích cỡ hay độ vừa vặn.</p>');
    else if(action==='chat') {
      const panel=document.querySelector('#chat-panel');
      panel.hidden=!panel.hidden;
      target.setAttribute('aria-expanded',String(!panel.hidden));
      const iframe=document.querySelector('#ami-avatar');
      if(!panel.hidden){
        if(!iframe.src)iframe.src=iframe.dataset.src;
        iframe.contentWindow?.postMessage({type:'may-ami-visible',visible:true},location.origin);
      }else{
        amiVoice.stop();iframe.contentWindow?.postMessage({type:'may-ami-visible',visible:false},location.origin);
      }
      if(!panel.hidden) {
        if(!document.querySelector('#chat-log').children.length) {
          const history=await api('/chat');
          if(history.length)history.forEach(m=>appendChat(m.sender,m.content,[],m.sender==='assistant'?m.id:null));
          else appendChat('assistant','Chào bạn, mình là Ami của mây. Bạn đang tìm món đồ nào? Cho mình biết phong cách và ngân sách để mình tư vấn nhé.');
        }
        document.querySelector('#chat-input').focus();
      }
    } else if(action==='chat-prompt') await sendChat(target.dataset.prompt);
    else if(action==='clear-chat') {chatGeneration++;chatRequest?.abort();chatRequest=null;chatBusy=false;amiVoice.clear();await api('/chat',{method:'DELETE'});document.querySelector('#chat-log').replaceChildren();document.querySelector('#chat-form [type="submit"]').disabled=false;appendChat('assistant','Đã xóa hội thoại. Ami có thể giúp gì cho bạn?');}
  } catch(err){toast(err.message);target.disabled=false;}
});

document.addEventListener('submit',async event=>{
  const form=event.target;
  if(!(form instanceof HTMLFormElement)) return;
  if(!['search-form','add-product-form','checkout-form','auth-form','chat-form'].includes(form.id)&&!form.matches('.stock-form,.admin-status-form'))return;
  event.preventDefault();
  const data=Object.fromEntries(new FormData(form));
  const submit=event.submitter;
  if(form.id==='search-form'){navigate('/shop?q='+encodeURIComponent(String(data.q).trim()));return;}
  if(form.id==='chat-form'){await sendChat(String(data.content));return;}
  const errorEl=form.querySelector('[role="alert"]');
  if(errorEl)errorEl.textContent='';
  if(submit)submit.disabled=true;
  try {
    if(form.id==='add-product-form'){
      const variant=selectedProduct.variants.find(v=>v.color===data.color&&v.size===data.size);
      if(!variant)throw new Error('Chưa có biến thể phù hợp. Hãy chọn màu và size khác.');
      cart=await api('/cart',json('POST',{variant_id:variant.id,quantity:Number(data.quantity)}));
      updateHeader();
      if(submit?.name==='buyNow')navigate('/checkout');else{openCart();toast('Đã thêm món đồ vào giỏ');}
    } else if(form.id==='auth-form'){
      await api('/auth/'+form.dataset.mode,json('POST',data));await refreshCustomer();modal.close();navigate(authDestination);toast('Chào mừng bạn đến với mây.');
    } else if(form.id==='checkout-form'){
      const voucher=String(data.voucher||'').trim().toUpperCase();
      if(voucher!==(checkoutQuote.voucher||''))throw new Error('Bạn đã thay đổi mã ưu đãi. Hãy nhấn Áp dụng và kiểm tra tổng tiền trước khi đặt hàng.');
      let order;
      try {
        order=await api('/orders',json('POST',{...data,voucher,idempotency_key:checkoutKey,expected_total:checkoutQuote.total}));
      } catch(error) {
        if(error instanceof ApiError && error.status===409 && error.detail?.code==='quote_changed'){
          checkoutQuote=error.detail.quote;
          checkoutKey=crypto.randomUUID();
          document.querySelector('#quote-summary').innerHTML=quoteMarkup(checkoutQuote);
          await refreshCart();
          document.querySelector('#checkout-products').innerHTML=checkoutProducts();
          throw new Error('Tổng tiền đã thay đổi. Hãy kiểm tra tổng tiền mới và nhấn Xác nhận đặt hàng lần nữa nếu đồng ý.');
        }
        throw error;
      }
      await refreshCart();
      if(order.payment_method==='online-demo')pendingPaymentId=order.id;
      navigate('/orders');toast('Đã tạo đơn hàng '+order.id);
    } else if(form.matches('.stock-form')){
      await api('/admin/variants/'+encodeURIComponent(form.dataset.id),json('PATCH',{stock:Number(data.stock)}));toast('Đã cập nhật tồn kho');products=await api('/products');
    } else if(form.matches('.admin-status-form')){
      await api('/admin/orders/'+form.dataset.id,json('PATCH',data));await renderRoute();toast('Đã cập nhật đơn hàng');
    }
  } catch(err){if(errorEl)errorEl.textContent=err.message;else toast(err.message);}
  finally{if(submit)submit.disabled=false;}
});

window.addEventListener('message',event=>{
  const iframe=document.querySelector('#ami-avatar');
  if(event.origin!==location.origin||event.source!==iframe?.contentWindow||event.data?.type!=='may-ami-status')return;
  document.querySelector('#ami-status').textContent=event.data.state==='ready'?'Sẵn sàng trò chuyện cùng bạn':String(event.data.message||'Chưa tải được nhân vật Ami.');
  if(event.data.state==='ready')iframe.contentWindow.postMessage({type:'may-ami-visible',visible:!document.querySelector('#chat-panel').hidden},location.origin);
});
document.addEventListener('change',event=>{
  if(event.target.id==='auto-read'){
    autoRead=event.target.checked;
    if(autoRead)amiVoice.unlock().catch(error=>{autoRead=false;event.target.checked=false;toast(error.message);});
    else amiVoice.stop();
  }
  if(event.target.id==='sort-products'){
    const [path,query]=(location.hash.slice(1)||'/shop').split('?');
    const params=new URLSearchParams(query);params.set('sort',event.target.value);navigate(path+'?'+params);
  }
  if(event.target.closest('#add-product-form')&&selectedProduct){
    const values=new FormData(document.querySelector('#add-product-form'));
    const variant=selectedProduct.variants.find(v=>v.color===values.get('color')&&v.size===values.get('size'));
    document.querySelector('#variant-stock').textContent=variant?variant.stock+' sản phẩm có sẵn':'Biến thể chưa có sẵn';
    document.querySelector('#product-quantity').max=String(Math.min(99,variant?.stock||0));
  }
});

modal.addEventListener('click',event=>{
  if(event.target!==modal)return;
  const rect=modal.getBoundingClientRect();
  if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)modal.close();
});
window.addEventListener('hashchange',renderRoute);

const reportUI=commerceUI({modal,toast,getCustomer:()=>customer,getProducts:()=>products,productGrid,refresh:async()=>{
  products=await api('/products');
  await refreshCart();
  await renderRoute();
}});

async function start() {
  try{
    const stored=JSON.parse(localStorage.getItem('may:saved')||'[]');
    if(Array.isArray(stored))saved=new Set(stored.filter(item=>typeof item==='string'));
  }catch(err){if(err instanceof SyntaxError)localStorage.removeItem('may:saved');else throw err;}
  try {
    customer=await api('/me');
    [products,categories,cart]=await Promise.all([api('/products'),api('/categories'),api('/cart')]);
    shell();updateHeader();await renderRoute();
  }catch(err){
    document.querySelector('#app').innerHTML='<div class="startup-error"><a class="logo" href="/">mây.</a><h1>Chưa kết nối được cửa hàng.</h1><p>'+esc(err.message)+'</p><p>Kiểm tra FastAPI đang chạy rồi tải lại trang.</p><a class="button primary" href="/">Tải lại</a></div>';
  }
}
start();
