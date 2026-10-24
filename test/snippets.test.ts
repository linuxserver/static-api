import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { parse } from 'yaml';
import type { Config } from '../src/api/types.ts';
import { dockerCompose, dockerRun } from '../src/snippets.ts';
import { fixtureModel } from './helpers.ts';

const config: Config = {
  hostname: { hostname: 'my host', desc: '', optional: true },
  caps: [{ cap_add: 'NET_ADMIN', desc: '', optional: false }],
  env_vars: [
    { name: 'PUID', value: '1000', desc: '', optional: false },
    { name: 'EXTRA', value: '', desc: '', optional: true },
  ],
  volumes: [{ path: '/config', host_path: '/path/to/config', desc: '', optional: false }],
  ports: [{ external: '51820', internal: '51820/udp', desc: '', optional: false }],
  custom: [
    { name: 'shm-size', name_compose: 'shm_size', value: '1gb', desc: '', optional: false },
    { name: 'sysctl', name_compose: 'sysctls', value: ['a=1', 'b=2'], desc: '', optional: false },
  ],
};

describe('dockerCompose', () => {
  it('writes a compose file with optional settings marked', () => {
    assert.equal(
      dockerCompose('wg', config),
      [
        '---',
        'services:',
        '  wg:',
        '    image: lscr.io/linuxserver/wg:latest',
        '    container_name: wg',
        '    hostname: "my host" # optional',
        '    cap_add:',
        '      - NET_ADMIN',
        '    environment:',
        '      - PUID=1000',
        '      - EXTRA= # optional',
        '    volumes:',
        '      - /path/to/config:/config',
        '    ports:',
        '      - 51820:51820/udp',
        '    shm_size: 1gb',
        '    sysctls:',
        '      - a=1',
        '      - b=2',
        '    restart: unless-stopped',
        '',
      ].join('\n'),
    );
  });

  it('drops port mappings with host networking', () => {
    const compose = dockerCompose('x', { ...config, networking: 'host' });
    assert.match(compose, /network_mode: host/);
    assert.doesNotMatch(compose, /ports:/);
  });

  it('is valid YAML for every fixture image', () => {
    for (const image of fixtureModel().images) {
      const doc = parse(image.snippets.docker_compose);
      assert.equal(doc.services[image.name].image, `lscr.io/linuxserver/${image.name}:latest`, image.name);
    }
  });
});

describe('dockerRun', () => {
  it('writes a docker run command with optional flags marked', () => {
    assert.equal(
      dockerRun('wg', config),
      [
        'docker run -d',
        '  --name=wg',
        '  --hostname=my host `#optional`',
        '  --cap-add=NET_ADMIN',
        '  -e PUID=1000',
        '  -e EXTRA= `#optional`',
        '  -p 51820:51820/udp',
        '  -v /path/to/config:/config',
        '  --shm-size=1gb',
        '  --sysctl=a=1',
        '  --sysctl=b=2',
        '  --restart unless-stopped',
        '  lscr.io/linuxserver/wg:latest',
      ].join(' \\\n') + '\n',
    );
  });

  it('includes privileged, networking and devices', () => {
    const run = dockerRun('x', {
      privileged: true,
      networking: 'host',
      ports: [{ external: '80', internal: '80', desc: '', optional: false }],
      devices: [{ path: '/dev/dri', host_path: '/dev/dri', desc: '', optional: true }],
    });
    assert.match(run, /--net=host/);
    assert.match(run, /--privileged/);
    assert.match(run, /--device \/dev\/dri:\/dev\/dri `#optional`/);
    assert.doesNotMatch(run, / -p /);
  });
});
