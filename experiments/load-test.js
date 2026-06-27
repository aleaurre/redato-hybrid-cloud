import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    constant_rate: {
      executor: 'constant-arrival-rate',
      rate: 10,
      timeUnit: '1s',
      duration: '2m',
      preAllocatedVUs: 20,
      maxVUs: 50,
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<5000'],
    http_req_failed: ['rate<0.10'],
  },
};

const TARGET = __ENV.TARGET || 'http://localhost:8080';

export default function () {
  const res = http.get(TARGET + '/hello');
  check(res, {
    'status is 200': (r) => r.status === 200,
  });
}
