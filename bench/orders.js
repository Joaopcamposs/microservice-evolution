// Cenário de carga padrão: cada VU cria um pedido (1-3 itens) e o consulta em seguida.
// Variáveis: VUS (padrão 50), DURATION (padrão 30s), BASE_URL (padrão http://api:8000).
import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.BASE_URL || 'http://api:8000';
const JSON_HEADERS = { headers: { 'Content-Type': 'application/json' } };

export const options = {
  vus: Number(__ENV.VUS || 50),
  duration: __ENV.DURATION || '30s',
  // Limiares sempre verdadeiros: só existem para o k6 exibir as métricas por endpoint.
  thresholds: {
    'http_req_duration{name:post_order}': ['max>=0'],
    'http_req_duration{name:get_order}': ['max>=0'],
  },
};

function post(path, body, name) {
  return http.post(`${BASE}${path}`, JSON.stringify(body), { ...JSON_HEADERS, tags: { name } });
}

// Massa fixa criada uma vez: poucos usuários e produtos, reaproveitados por todos os VUs.
export function setup() {
  const run = Date.now();
  const users = [];
  const products = [];
  for (let i = 0; i < 10; i++) {
    const user = post('/users', { name: `bench ${i}`, email: `bench-${run}-${i}@mail.com`, password: 'senha-forte-1' }, 'setup');
    users.push(user.json('id'));
    const product = post('/products', { name: `produto ${i}`, price_cents: 1000 + i }, 'setup');
    products.push(product.json('id'));
  }
  return { users, products };
}

const pick = (list) => list[Math.floor(Math.random() * list.length)];

export default function (data) {
  // 1-3 produtos distintos, quantidade 1-3 (a API rejeita produto repetido).
  const count = 1 + Math.floor(Math.random() * 3);
  const start = Math.floor(Math.random() * data.products.length);
  const items = [];
  for (let i = 0; i < count; i++) {
    items.push({ product_id: data.products[(start + i) % data.products.length], quantity: 1 + Math.floor(Math.random() * 3) });
  }

  const created = post('/orders', { user_id: pick(data.users), items }, 'post_order');
  const ok = check(created, { 'POST /orders = 201': (r) => r.status === 201 });
  if (!ok) return;

  const found = http.get(`${BASE}/orders?id=${created.json('id')}`, { tags: { name: 'get_order' } });
  check(found, { 'GET /orders?id = 200 com 1 item': (r) => r.status === 200 && r.json().length === 1 });
}
