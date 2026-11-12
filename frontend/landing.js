import { esc, imagePath, money } from './api.js';
import { icon } from './icons.js';

/** @param {import('./api.js').Product[]} products */
export function landingPage(products) {
  const shirt = products.find(product => product.id === '8tp26a003');
  return '<section class="landing-hero" aria-labelledby="landing-title">' +
    '<div class="landing-copy"><p class="landing-kicker"><span></span> MẶC ĐẸP BẮT ĐẦU TỪ ĐÚNG GU</p>' +
    '<h1 id="landing-title">Tìm được áo<br><em>ưng ý.</em><br>Vẫn là <span>chính mình.</span></h1>' +
    '<p class="landing-description">Chiếc áo đã chọn. Bữa sáng còn dang dở.<br>Giữa những điều rất thường, anh tìm thấy gu của mình.</p>' +
    '<button id="landing-shop" class="button landing-primary" data-action="enter-shop">Đăng nhập & tìm gu của bạn ' + icon('arrow') + '</button>' +
    '<p class="landing-signup">Lần đầu ghé mây? <button data-action="landing-register">Tạo tài khoản</button></p>' +
    '<div class="landing-note">' + icon('heart') + '<span>Chọn vì bạn thích.<br>Mặc vì bạn thấy là mình.</span></div>' +
    '<div class="landing-music-intro"><button id="landing-music-toggle" data-action="landing-music" aria-controls="landing-music-panel" aria-expanded="false">' + icon('music') + '<span>Bật nhạc cùng mây</span></button><small>Earrings · Malcolm Todd</small></div></div>' +
    '<figure class="landing-photo"><img id="landing-story-photo" src="/static/assets/landing-story.jpeg" alt="Chàng trai đeo kính đang nấu ăn trong căn bếp màu hồng" width="940" height="1672" fetchpriority="high">' +
    '<figcaption><span class="landing-photo-label">MỘT CHÚT ĐỜI THƯỜNG. MỘT CHÚT MÂY.</span><strong>Áo đã chọn.<br>Bữa sáng vẫn đang làm.</strong></figcaption>' +
    '<span class="landing-stamp">ĐÃ TÌM ĐƯỢC<br><b>áo ưng ý</b>' + icon('heart') + '</span></figure></section>' +
    '<section id="landing-discover" class="landing-story" aria-labelledby="landing-story-title"><div class="landing-story-heading"><p class="landing-kicker">CHUYỆN MẶC ĐẸP CÙNG MÂY</p><h2 id="landing-story-title">Một chiếc áo.<br>Một buổi sáng.<br>Một người <em>rất riêng.</em></h2><p>Đọc chậm một chút.<br>Biết đâu, bạn gặp mình trong đó.</p><span class="landing-story-flower" aria-hidden="true">✳</span></div>' +
    '<div class="landing-story-content"><article><h3>Buổi sáng ấy, anh chưa vội.</h3>' +
    '<p>Nắng ghé qua ô cửa, nằm nghiêng trên mấy viên gạch hồng. Trong chảo, một quả trứng vừa chạm dầu đã reo lên khe khẽ. Anh chỉnh lại gọng kính, nghiêng người tìm chiếc đĩa quen. Một bài nhạc vẫn đang chạy. Bữa sáng chỉ còn thiếu chút tiêu, còn ngày hôm ấy thì chưa cần phải có kế hoạch gì thật lớn.</p>' +
    '<p>Điện thoại sáng lên bên cạnh. Trên màn hình là chiếc áo anh đã chọn từ tối qua. Anh liếc nhìn, mỉm cười, rồi quay lại với cái chảo. Sau khá nhiều lần mở tủ và đứng nghĩ mãi trước những món đồ quen thuộc, cuối cùng anh cũng có một thứ khiến mình mong đến lúc được mặc thử.</p></article>' +
    '<article><h3>Trước đó là những lần “để xem thêm”.</h3>' +
    '<p>Anh từng lưu nhiều chiếc áo. Có chiếc nhìn rất hay khi người khác mặc, có chiếc khiến anh dừng lại vì một màu đẹp. Nhưng đến lúc hình dung mình mặc nó đi uống cà phê, ghé hiệu sách hay gặp bạn bè, anh lại ngập ngừng. Thế là để xem thêm. Rồi quên mất. Những buổi sáng trước tủ đồ vẫn cứ giống nhau.</p>' +
    '<p>Một tối, anh ghé mây. Lần này, anh bắt đầu bằng những điều mình biết rõ: thích màu dễ phối, thích cảm giác thoải mái, muốn một chiếc áo có thể mặc vào nhiều ngày bình thường. Anh kể với Ami cả khoảng giá mình đang tìm. Vài gợi ý xuất hiện, vừa đủ để anh xem kỹ từng món, đối chiếu thông tin và giữ lại những lựa chọn thật sự muốn mặc.</p>' +
    '<p>Anh dừng lâu hơn ở một chiếc áo. Nhìn lại màu, xem thêm size, nghĩ đến chiếc quần vẫn thường mặc. Trong đầu anh hiện ra một buổi chiều rất cụ thể: quán quen, bàn sát cửa sổ, bạn bè đã ngồi đợi. Và anh, trong chiếc áo ấy, bước vào một cách tự nhiên.</p></article>' +
    '<article><h3>Rồi chiếc áo cũng có một chỗ trong ngày.</h3>' +
    '<p>Anh chọn nó. Cảm giác nhẹ nhõm đến từ một việc nhỏ: đã tìm thấy món đồ mình có lý do để thích. Chiếc áo ấy có thể đi cùng những thứ sẵn có trong tủ, theo anh đến những cuộc hẹn quen và cả những lần bước ra ngoài chỉ để mua một ly cà phê.</p>' +
    '<p>Đến buổi sáng trong căn bếp hồng, nghĩ lại chuyện chọn áo vẫn làm anh vui. Anh vẫn đeo cặp kính ấy, nghe bài nhạc ấy, và vẫn hơi vụng khi lật trứng. Có người gọi từ phía cửa, anh ngoảnh lại. Một khoảnh khắc được giữ lại, giữa lúc bữa sáng còn đang làm và chiếc áo ưng ý vừa được tìm thấy.</p>' +
    '<p>Ở mây, chúng mình thích những câu chuyện nhỏ như thế. Một người tìm được món đồ muốn mặc. Một buổi sáng bớt đi vài phút phân vân. Một cuộc hẹn có thêm điều để mong. Từng chút một, tủ đồ trở thành nơi có những lựa chọn khiến bạn thấy dễ chịu mỗi khi mở cửa.</p></article>' +
    '<p class="landing-story-ending">Bữa sáng rồi sẽ xong.<br>Bài nhạc rồi sẽ sang đoạn mới.<br>Còn câu chuyện về chiếc áo của bạn,<br><em>có thể bắt đầu ngay hôm nay.</em></p>' +
    '<button class="text-link landing-story-cta" data-action="enter-shop">Tìm chiếc áo cho câu chuyện của bạn ' + icon('arrow') + '</button></div></section>' +
    '<section class="landing-discover" aria-labelledby="landing-discover-title"><div class="landing-discover-heading"><p class="landing-kicker">TỪ MỘT CHIẾC ÁO, ĐẾN GU CỦA BẠN</p><h2 id="landing-discover-title">Không cần cầu kỳ.<br>Chỉ cần <em>hợp mình.</em></h2></div>' +
    '<div class="landing-ways"><div>' + icon('search') + '<h3>Tìm điều bạn thích</h3><p>Gõ tên món đồ hoặc nói bằng giọng nói. Mây giúp bạn tìm trong tủ đồ hiện có.</p></div><div>' + icon('sparkle') + '<h3>Thử phối theo cách bạn</h3><p>Bật camera, thử phối áo và phụ kiện trước khi chọn món mình thích.</p></div><div>' + icon('chat') + '<h3>Có Ami cùng chọn</h3><p>Kể gu, ngân sách và điều bạn đang tìm. Ami sẽ gợi ý từ sản phẩm của mây.</p></div></div></section>' +
    '<section class="landing-invitation"><div><p class="landing-kicker">CHIẾC ÁO TIẾP THEO, CÓ THỂ Ở ĐÂY.</p><h2>Tủ đồ mới.<br><em>Vẫn là bạn.</em></h2><p>Đăng nhập để xem sản phẩm, chọn size<br>và lưu những món đồ hợp gu.</p><button class="text-link" data-action="enter-shop">Vào mua sắm cùng mây ' + icon('arrow') + '</button></div>' +
    (shirt ? '<div class="landing-shirt"><img src="' + imagePath(shirt.image) + '" alt="' + esc(shirt.name) + '" width="400" height="500" loading="lazy"><div><span>GỢI Ý TỪ MÂY · ' + esc(shirt.brand) + '</span><h3>' + esc(shirt.name) + '</h3><strong>' + money(shirt.price) + '</strong></div></div>' : '') +
    '</section><div class="landing-footer"><a class="logo" href="#/">mây<span>.</span></a><span>Mặc điều bạn thích. Theo cách của bạn.</span><small>© 2026 mây. · Bản demo học tập</small></div>' +
    '<aside id="landing-music-panel" class="landing-music-panel" aria-labelledby="landing-music-title" hidden><div class="landing-music-heading"><div><span>NHẠC CÙNG MÂY</span><h2 id="landing-music-title">Earrings · Malcolm Todd</h2></div><button id="landing-music-close" class="icon-button" data-action="landing-music" aria-label="Tắt nhạc và đóng trình phát">' + icon('close') + '</button></div><div class="landing-music-frame"></div><p>Nếu chưa nghe nhạc, nhấn ▶ trong trình phát. <a href="https://www.youtube.com/watch?v=a4tdS3IB294" target="_blank" rel="noopener">Mở trên YouTube ' + icon('arrow') + '</a></p></aside>';
}

export function toggleLandingMusic() {
  const panel = document.querySelector('#landing-music-panel');
  const button = document.querySelector('#landing-music-toggle');
  const frame = panel.querySelector('.landing-music-frame');
  if (!panel.hidden) {
    frame.replaceChildren();
    panel.hidden = true;
    button.setAttribute('aria-expanded', 'false');
    button.querySelector('span').textContent = 'Bật nhạc cùng mây';
    button.focus({preventScroll:true});
    return;
  }
  const player = document.createElement('iframe');
  const parameters = new URLSearchParams({autoplay:'1',loop:'1',playlist:'a4tdS3IB294',playsinline:'1',rel:'0',origin:location.origin});
  player.id = 'landing-music-player';
  player.title = 'Earrings — Malcolm Todd · Trình phát YouTube';
  player.width = '320';
  player.height = '200';
  player.allow = 'autoplay; encrypted-media; picture-in-picture; fullscreen';
  // YouTube requires the embedding origin as a referrer for player identification.
  player.referrerPolicy = 'strict-origin-when-cross-origin';
  player.src = 'https://www.youtube.com/embed/a4tdS3IB294?' + parameters;
  panel.hidden = false;
  frame.append(player);
  button.setAttribute('aria-expanded', 'true');
  button.querySelector('span').textContent = 'Tắt nhạc';
}
