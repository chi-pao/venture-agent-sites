// React を使っていないページに ElectricLogo（React Bits）を1つ置くための入口。
// tools/build_electric_logo.sh で checker-site/vendor/electric-logo.js にまとめる。
import { createElement } from 'react';
import { createRoot } from 'react-dom/client';
import ElectricLogo from './ElectricLogo';

export function mount(el, props) {
  const root = createRoot(el);
  root.render(createElement(ElectricLogo, props));
  return () => root.unmount();
}
