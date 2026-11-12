/**
 * @typedef {{id:string,color:string,size:string,price:number,stock:number}} Variant
 * @typedef {{id:string,name:string,brand:string,category:string,price:number,original_price:number,image:string,rating:number|null,sold:number|null,try_on:string|null,tag:string,specs:Record<string,string>,variants:Variant[],source_url?:string|null,collected_at?:string|null}} Product
 * @typedef {{variant_id:string,product_id:string,name:string,image:string,color:string,size:string,price:number,stock:number,quantity:number}} CartLine
 */

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

/** @template T @param {string} path @param {RequestInit} [options] @returns {Promise<T>} */
export async function api(path, options = {}) {
  const response = await fetch('/api' + path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    const message = typeof detail === 'string' ? detail :
      Array.isArray(detail) ? detail.map(item => item.loc.at(-1) + ': ' + item.msg).join('; ') :
      detail?.message || 'Không hoàn tất được yêu cầu (HTTP ' + response.status + ').';
    throw new ApiError(message, response.status, detail);
  }
  return data;
}

/** @param {string} method @param {object} data @returns {RequestInit} */
export const json = (method, data) => ({ method, body: JSON.stringify(data) });
/** @param {number} value */
export const money = value => new Intl.NumberFormat('vi-VN').format(value) + '₫';
/** @param {string|number} value */
export const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
/** @param {string} image */
export const imagePath = image => '/static/assets/' + image + (/\.(webp|png|jpe?g)$/.test(image) ? '' : '.svg');
