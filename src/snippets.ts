/**
 * Quick-start snippets generated from an image's config, in the same shape as the READMEs and
 * docs.linuxserver.io. Ported from the site (src/lib/images.ts) so both produce identical output;
 * optional parameters are included and marked as such.
 */
import type { Config } from './api/types.ts';

export const REGISTRY = 'lscr.io/linuxserver';

/** Quote a YAML scalar only when it needs it. */
const q = (s: string) => (/[\s:#{}[\],&*?|<>=!%@`'"]/.test(s) || s === '' ? JSON.stringify(s) : s);

/** Port mappings are meaningless with host networking. */
const portsFor = (c: Config) => (c.networking === 'host' ? [] : (c.ports ?? []));

export function dockerCompose(name: string, c: Config): string {
  const opt = (x: { optional: boolean }) => (x.optional ? ' # optional' : '');
  const lines = [
    '---',
    'services:',
    `  ${name}:`,
    `    image: ${REGISTRY}/${name}:latest`,
    `    container_name: ${name}`,
  ];
  const list = <T extends { optional: boolean }>(key: string, xs: T[] | undefined, value: (x: T) => string) => {
    if (xs?.length) lines.push(`    ${key}:`, ...xs.map((x) => `      - ${value(x)}${opt(x)}`));
  };

  if (c.networking) lines.push(`    network_mode: ${c.networking}`);
  if (c.privileged) lines.push('    privileged: true');
  if (c.hostname) lines.push(`    hostname: ${q(c.hostname.hostname)}${opt(c.hostname)}`);
  if (c.mac_address) lines.push(`    mac_address: ${q(c.mac_address.mac_address)}${opt(c.mac_address)}`);
  list('cap_add', c.caps, (x) => x.cap_add);
  list('security_opt', c.security_opt, (x) => x.compose_var);
  list('environment', c.env_vars, (e) => `${e.name}=${e.value}`);
  list('volumes', c.volumes, (v) => `${v.host_path}:${v.path}`);
  list('ports', portsFor(c), (p) => `${p.external}:${p.internal}`);
  list('devices', c.devices, (d) => `${d.host_path}:${d.path}`);
  for (const x of c.custom ?? []) {
    if (Array.isArray(x.value)) lines.push(`    ${x.name_compose}:`, ...x.value.map((v) => `      - ${v}`));
    else lines.push(`    ${x.name_compose}: ${q(x.value)}${opt(x)}`);
  }
  lines.push('    restart: unless-stopped');
  return lines.join('\n') + '\n';
}

export function dockerRun(name: string, c: Config): string {
  const opt = (x: { optional: boolean }) => (x.optional ? ' `#optional`' : '');
  const lines = ['docker run -d', `  --name=${name}`];
  if (c.networking) lines.push(`  --net=${c.networking}`);
  if (c.privileged) lines.push('  --privileged');
  if (c.hostname) lines.push(`  --hostname=${c.hostname.hostname}${opt(c.hostname)}`);
  if (c.mac_address) lines.push(`  --mac-address=${c.mac_address.mac_address}${opt(c.mac_address)}`);
  for (const x of c.caps ?? []) lines.push(`  --cap-add=${x.cap_add}${opt(x)}`);
  for (const x of c.security_opt ?? []) lines.push(`  --security-opt ${x.run_var}${opt(x)}`);
  for (const e of c.env_vars ?? []) lines.push(`  -e ${e.name}=${e.value}${opt(e)}`);
  for (const p of portsFor(c)) lines.push(`  -p ${p.external}:${p.internal}${opt(p)}`);
  for (const v of c.volumes ?? []) lines.push(`  -v ${v.host_path}:${v.path}${opt(v)}`);
  for (const d of c.devices ?? []) lines.push(`  --device ${d.host_path}:${d.path}${opt(d)}`);
  for (const x of c.custom ?? []) {
    for (const v of Array.isArray(x.value) ? x.value : [x.value]) lines.push(`  --${x.name}=${v}${opt(x)}`);
  }
  lines.push('  --restart unless-stopped', `  ${REGISTRY}/${name}:latest`);
  return lines.join(' \\\n') + '\n';
}
