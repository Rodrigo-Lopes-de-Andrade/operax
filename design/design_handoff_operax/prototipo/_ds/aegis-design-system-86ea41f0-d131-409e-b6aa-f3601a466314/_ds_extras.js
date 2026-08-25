/* @ds-extras: components added for OperaX (Table, Chart, Drawer, Tabs, EmptyState,
   Toast, Skeleton, Pagination). Registers into the same namespace as _ds_bundle.js.
   Plain JS + React.createElement — loads with a normal <script src>, after the bundle. */

(() => {
const ns = (window.AegisDesignSystem_86ea41 = window.AegisDesignSystem_86ea41 || {});
const h = (...args) => React.createElement(...args);
const Icon = (name, size, color) => ns.Icon ? h(ns.Icon, { name, size, color }) : null;

const TONE_FG = {
  neutral: 'var(--text-muted)', good: 'var(--good-foreground)', bad: 'var(--bad-foreground)',
  alert: 'var(--alert-foreground)', brand: 'var(--brand-strong)', violet: 'var(--accent-violet)', orange: 'var(--accent-orange)',
};
const TONE_BG = {
  neutral: 'var(--surface-muted)', good: 'var(--good-background)', bad: 'var(--bad-background)',
  alert: 'var(--alert-background)', brand: 'var(--brand-soft)', violet: 'rgba(31,122,138,0.14)', orange: 'rgba(194,65,12,0.12)',
};

/* ---------------------------------------------------------------- Skeleton */
function Skeleton({ width = '100%', height = 14, radius = 'var(--radius-xs)', lines = 1, gap = 8, style = {} }) {
  const bar = (i) => h('span', {
    key: i,
    style: {
      display: 'block', width: lines > 1 && i === lines - 1 ? '64%' : width, height,
      borderRadius: radius, background: 'linear-gradient(90deg, rgba(17,29,45,0.06) 25%, rgba(17,29,45,0.11) 37%, rgba(17,29,45,0.06) 63%)',
      backgroundSize: '400% 100%', animation: 'aegis-skeleton 1.4s ease-in-out infinite',
    },
  });
  return h('span', { style: { display: 'flex', flexDirection: 'column', gap, ...style } },
    Array.from({ length: lines }, (_, i) => bar(i)));
}

/* -------------------------------------------------------------- EmptyState */
function EmptyState({ icon = 'inbox', title, description, tone = 'neutral', children, compact = false, style = {} }) {
  return h('div', {
    style: {
      background: 'var(--surface-card)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-xl)',
      boxShadow: 'var(--shadow-sm)', padding: compact ? '32px 24px' : '56px 40px', display: 'flex',
      flexDirection: 'column', alignItems: 'center', textAlign: 'center', gap: 6, ...style,
    },
  },
    h('span', {
      style: {
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: compact ? 44 : 64,
        height: compact ? 44 : 64, borderRadius: 'var(--radius-full)', marginBottom: 8,
        background: TONE_BG[tone], color: TONE_FG[tone],
      },
    }, Icon(icon, compact ? 21 : 29)),
    h('h3', { style: { fontSize: compact ? 'var(--text-md)' : 'var(--text-xl)', fontWeight: 700, color: 'var(--text-strong)' } }, title),
    description ? h('p', {
      style: { fontSize: 'var(--text-sm)', color: 'var(--text-muted)', maxWidth: 520, textWrap: 'pretty', lineHeight: 'var(--leading-relaxed)' },
    }, description) : null,
    children ? h('div', { style: { display: 'flex', gap: 10, marginTop: 12, flexWrap: 'wrap', justifyContent: 'center' } }, children) : null);
}

/* ------------------------------------------------------------------- Table */
function cellNode(col, row) {
  const v = row[col.key];
  const align = col.align === 'right' ? 'right' : col.align === 'center' ? 'center' : 'left';
  if (v === null || v === undefined || v === '') return h('span', { style: { color: 'var(--text-faint)' } }, '—');

  if (typeof v === 'object' && v.kind) {
    if (v.kind === 'badge') {
      return ns.Badge ? h(ns.Badge, { tone: v.tone || 'neutral', size: 'sm', dot: v.dot }, v.label) : v.label;
    }
    if (v.kind === 'stack') {
      return h('div', { style: { display: 'flex', alignItems: 'center', gap: 10 } },
        v.dot ? h('span', { style: { width: 8, height: 8, borderRadius: '50%', flex: 'none', background: v.dot } }) : null,
        h('div', { style: { minWidth: 0 } },
          h('div', { style: { fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-strong)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' } }, v.title),
          v.sub ? h('div', { style: { fontSize: 'var(--text-2xs)', color: 'var(--text-faint)', marginTop: 1 } }, v.sub) : null),
        v.chip ? h(Chip, { label: v.chip, icon: v.chipIcon }) : null);
    }
    if (v.kind === 'signed') {
      return h('div', { style: { display: 'flex', flexDirection: 'column', alignItems: align === 'right' ? 'flex-end' : 'flex-start' } },
        h('span', {
          className: 'aegis-tnum',
          style: { fontSize: 'var(--text-sm)', fontWeight: 700, color: v.color || (String(v.value).startsWith('-') || String(v.value).startsWith('\u2212') ? 'var(--accent-orange)' : 'var(--accent-violet)') },
        }, v.value),
        v.sub ? h('span', { style: { fontSize: 'var(--text-2xs)', color: 'var(--text-faint)' } }, v.sub) : null);
    }
    if (v.kind === 'textchip') {
      return h('div', { style: { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' } },
        h('span', { style: { fontSize: 'var(--text-sm)', color: 'var(--text-body)' } }, v.label),
        v.chip ? h(Chip, { label: v.chip, icon: v.chipIcon }) : null);
    }
    if (v.kind === 'chip') return h(Chip, { label: v.label, icon: v.icon });
    if (v.kind === 'check') {
      return ns.Checkbox ? h('span', {
        style: { display: 'inline-flex' },
        onClick: (e) => e.stopPropagation(),
      }, h(ns.Checkbox, {
        checked: !!v.checked, disabled: v.disabled,
        onChange: (next) => { if (v.onChange) v.onChange(next); },
      })) : null;
    }
    if (v.kind === 'button') {
      return ns.Button ? h(ns.Button, {
        variant: v.variant || 'secondary', size: 'sm', icon: v.icon, disabled: v.disabled,
        onClick: (e) => { if (e && e.stopPropagation) e.stopPropagation(); if (v.onClick) v.onClick(); },
      }, v.label) : null;
    }
    if (v.kind === 'bar') {
      return h('div', { style: { display: 'flex', alignItems: 'center', gap: 8, justifyContent: align === 'right' ? 'flex-end' : 'flex-start' } },
        h('span', { className: 'aegis-tnum', style: { fontSize: 'var(--text-sm)', color: 'var(--text-body)', minWidth: 40, textAlign: 'right' } }, v.label),
        h('span', { style: { width: v.width || 76, height: 6, borderRadius: 'var(--radius-pill)', background: 'rgba(17,29,45,0.08)', overflow: 'hidden' } },
          h('span', { style: { display: 'block', height: '100%', width: (v.pct || 0) + '%', background: v.color || 'var(--brand)' } })));
    }
    if (v.kind === 'time') {
      return h('div', null,
        h('div', { className: 'aegis-mono', style: { fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-strong)' } }, v.label),
        v.sub ? h('div', { style: { fontSize: 'var(--text-2xs)', color: 'var(--text-faint)' } }, v.sub) : null);
    }
  }

  const cls = col.mono ? 'aegis-mono' : col.numeric ? 'aegis-tnum' : undefined;
  return h('span', {
    className: cls,
    style: {
      fontSize: 'var(--text-sm)', fontWeight: col.strong ? 600 : 400,
      color: col.strong ? 'var(--text-strong)' : col.muted ? 'var(--text-muted)' : 'var(--text-body)',
    },
  }, v);
}

function Chip({ label, icon }) {
  return h('span', {
    style: {
      display: 'inline-flex', alignItems: 'center', gap: 5, height: 20, padding: '0 8px', flex: 'none',
      borderRadius: 'var(--radius-pill)', border: '1px dashed var(--border-strong)', background: 'var(--surface-muted)',
      fontSize: 'var(--text-2xs)', fontWeight: 600, color: 'var(--text-muted)', whiteSpace: 'nowrap',
    },
  }, icon ? Icon(icon, 11) : null, label);
}

/**
 * Table — the backbone surface of the product.
 * columns: [{ key, label, align, width, strong, muted, mono, numeric, sortable, noWrap }]
 * rows:    [{ ...values, id?, onClick?, tone?, muted? }]  values may be strings or
 *          descriptors: {kind:'badge'|'stack'|'signed'|'chip'|'bar'|'time', ...}
 */
function Table({
  columns = [], rows = [], density = 'default', stickyHeader = false, maxHeight,
  sortKey, sortDir = 'desc', onSort, onRowClick, empty, footer, zebra = false, style = {},
}) {
  const [hoverRow, setHoverRow] = React.useState(-1);
  const [innerSort, setInnerSort] = React.useState(null);
  const active = onSort ? { key: sortKey, dir: sortDir } : (innerSort || { key: sortKey, dir: sortDir });
  const padY = density === 'compact' ? 8 : density === 'relaxed' ? 16 : 12;
  const padX = 16;

  const sorted = React.useMemo(() => {
    if (onSort || !active.key) return rows;
    const col = columns.find((c) => c.key === active.key);
    if (!col || !col.sortable) return rows;
    const raw = (r) => {
      const v = r[active.key];
      const s = v && typeof v === 'object' ? (v.value ?? v.label ?? v.title ?? '') : v;
      const n = parseFloat(String(s).replace(/[^\d.,\-\u2212]/g, '').replace('\u2212', '-').replace(',', '.'));
      return isNaN(n) ? String(s).toLowerCase() : n;
    };
    return [...rows].sort((a, b) => {
      const x = raw(a); const y = raw(b);
      if (x === y) return 0;
      return (x > y ? 1 : -1) * (active.dir === 'asc' ? 1 : -1);
    });
  }, [rows, active.key, active.dir, onSort, columns]);

  const head = h('thead', { style: stickyHeader ? { position: 'sticky', top: 0, zIndex: 2 } : null },
    h('tr', { style: { background: 'var(--surface-muted)' } },
      columns.map((c, i) => {
        const isActive = active.key === c.key;
        const click = c.sortable ? () => {
          const dir = isActive && active.dir === 'desc' ? 'asc' : 'desc';
          if (onSort) onSort(c.key, dir); else setInnerSort({ key: c.key, dir });
        } : undefined;
        return h('th', {
          key: c.key,
          onClick: click,
          style: {
            textAlign: c.align || 'left', padding: `10px ${i === 0 ? 22 : padX}px`, width: c.width,
            fontSize: 'var(--text-2xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em',
            color: isActive ? 'var(--text-strong)' : 'var(--text-muted)', whiteSpace: 'nowrap',
            cursor: c.sortable ? 'pointer' : 'default', userSelect: 'none',
            background: 'var(--surface-muted)', borderBottom: '1px solid var(--border-subtle)',
          },
        }, h('span', { style: { display: 'inline-flex', alignItems: 'center', gap: 4, justifyContent: c.align === 'right' ? 'flex-end' : 'flex-start' } },
          c.label,
          c.sortable ? Icon(isActive ? (active.dir === 'asc' ? 'arrow-up' : 'arrow-down') : 'chevrons-up-down', 12) : null));
      })));

  const body = h('tbody', null, sorted.map((r, ri) => {
    const clickable = !!(r.onClick || onRowClick);
    const go = r.onClick || (onRowClick ? () => onRowClick(r, ri) : undefined);
    return h('tr', {
      key: r.id || ri,
      onClick: go,
      onMouseEnter: () => setHoverRow(ri),
      onMouseLeave: () => setHoverRow(-1),
      style: {
        borderTop: '1px solid var(--border-subtle)', cursor: clickable ? 'pointer' : 'default',
        background: hoverRow === ri && clickable ? 'var(--surface-muted)' : zebra && ri % 2 ? 'rgba(17,29,45,0.015)' : 'transparent',
        opacity: r.muted ? 0.72 : 1,
        transition: 'background var(--duration-fast) var(--ease-standard)',
      },
    }, columns.map((c, ci) => h('td', {
      key: c.key,
      style: {
        padding: `${padY}px ${ci === 0 ? 22 : padX}px`, textAlign: c.align || 'left',
        whiteSpace: c.noWrap ? 'nowrap' : 'normal', verticalAlign: 'middle',
      },
    }, cellNode(c, r))));
  }));

  if (!rows.length && empty) {
    return h('div', { style: { padding: 4, ...style } }, h(EmptyState, Object.assign({ compact: true }, empty)));
  }

  const table = h('table', { style: { width: '100%', borderCollapse: 'collapse' } }, head, body);
  return h('div', { style: Object.assign({ width: '100%', overflow: maxHeight ? 'auto' : 'visible', maxHeight }, style) },
    table,
    footer ? h('div', { style: { borderTop: '1px solid var(--border-subtle)' } }, footer) : null);
}

/* -------------------------------------------------------------- Pagination */
function Pagination({ page = 1, pageCount = 1, total, pageSize = 25, onPage, onPageSize, sizes = [25, 50, 100], label = 'registros' }) {
  const btn = (icon, disabled, to, aria) => h('button', {
    type: 'button', disabled, onClick: disabled ? undefined : () => onPage && onPage(to), 'aria-label': aria,
    style: {
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 30, height: 30,
      borderRadius: 'var(--radius-md)', border: '1px solid var(--control-border)',
      background: disabled ? 'var(--control-disabled-bg)' : 'var(--surface-card)',
      color: disabled ? 'var(--control-disabled-fg)' : 'var(--text-body)',
      cursor: disabled ? 'default' : 'pointer',
    },
  }, Icon(icon, 15));
  return h('div', {
    style: {
      display: 'flex', alignItems: 'center', gap: 14, padding: '12px 22px', flexWrap: 'wrap',
      fontSize: 'var(--text-xs)', color: 'var(--text-muted)',
    },
  },
    total !== undefined ? h('span', { className: 'aegis-tnum' }, `${total} ${label}`) : null,
    onPageSize ? h('span', { style: { display: 'inline-flex', alignItems: 'center', gap: 6 } },
      'Por página',
      h('span', { style: { display: 'inline-flex', gap: 2, background: 'var(--surface-muted)', borderRadius: 'var(--radius-pill)', padding: 2 } },
        sizes.map((s) => h('button', {
          key: s, type: 'button', onClick: () => onPageSize(s),
          style: {
            border: 'none', cursor: 'pointer', borderRadius: 'var(--radius-pill)', padding: '3px 9px',
            fontFamily: 'var(--font-mono)', fontSize: 'var(--text-2xs)', fontWeight: 700,
            background: s === pageSize ? 'var(--surface-card)' : 'transparent',
            color: s === pageSize ? 'var(--text-strong)' : 'var(--text-muted)',
            boxShadow: s === pageSize ? 'var(--shadow-sm)' : 'none',
          },
        }, s)))) : null,
    h('span', { style: { flex: 1 } }),
    h('span', { className: 'aegis-tnum', style: { color: 'var(--text-body)' } }, `Página ${page} de ${pageCount}`),
    h('span', { style: { display: 'inline-flex', gap: 6 } },
      btn('chevron-left', page <= 1, page - 1, 'Página anterior'),
      btn('chevron-right', page >= pageCount, page + 1, 'Próxima página')));
}

/* -------------------------------------------------------------------- Tabs */
function Tabs({ tabs = [], value, onChange, style = {} }) {
  return h('div', {
    role: 'tablist',
    style: Object.assign({ display: 'flex', gap: 4, borderBottom: '1px solid var(--border-subtle)', overflowX: 'auto' }, style),
  }, tabs.map((t) => {
    const sel = t.value === value;
    return h('button', {
      key: t.value, role: 'tab', 'aria-selected': sel, type: 'button',
      onClick: () => onChange && onChange(t.value),
      style: {
        display: 'inline-flex', alignItems: 'center', gap: 8, padding: '11px 14px', border: 'none',
        background: 'transparent', cursor: 'pointer', fontFamily: 'var(--font-sans)',
        fontSize: 'var(--text-sm)', fontWeight: sel ? 700 : 500,
        color: sel ? 'var(--text-strong)' : 'var(--text-muted)',
        boxShadow: sel ? 'inset 0 -2px 0 0 var(--brand)' : 'none', whiteSpace: 'nowrap',
      },
    },
      t.icon ? Icon(t.icon, 16) : null,
      t.label,
      t.count !== undefined && t.count !== null ? h('span', {
        className: 'aegis-tnum',
        style: {
          fontSize: 'var(--text-2xs)', fontWeight: 700, padding: '1px 7px', borderRadius: 'var(--radius-pill)',
          background: sel ? 'var(--brand-soft)' : 'var(--surface-muted)', color: sel ? 'var(--brand-strong)' : 'var(--text-muted)',
        },
      }, t.count) : null);
  }));
}

/* ------------------------------------------------------------------- Toast */
function Toast({ tone = 'neutral', title, description, action, actionLabel, onClose, icon, style = {} }) {
  const glyph = icon || { good: 'check-circle-2', bad: 'octagon-alert', alert: 'triangle-alert', brand: 'info' }[tone] || 'info';
  return h('div', {
    role: 'status',
    style: Object.assign({
      display: 'flex', alignItems: 'flex-start', gap: 12, padding: '14px 16px', maxWidth: 460,
      background: 'var(--surface-card)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-lg)',
      boxShadow: 'var(--shadow-lg)',
    }, style),
  },
    h('span', {
      style: {
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 30, height: 30, flex: 'none',
        borderRadius: 'var(--radius-md)', background: TONE_BG[tone], color: TONE_FG[tone],
      },
    }, Icon(glyph, 17)),
    h('div', { style: { flex: 1, minWidth: 0 } },
      h('div', { style: { fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--text-strong)' } }, title),
      description ? h('div', { style: { fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: 2, textWrap: 'pretty' } }, description) : null,
      action ? h('button', {
        type: 'button', onClick: action,
        style: {
          marginTop: 8, border: 'none', background: 'transparent', padding: 0, cursor: 'pointer',
          fontFamily: 'var(--font-sans)', fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--brand-strong)',
        },
      }, actionLabel || 'Desfazer') : null),
    onClose ? h('button', {
      type: 'button', onClick: onClose, 'aria-label': 'Fechar',
      style: { border: 'none', background: 'transparent', cursor: 'pointer', color: 'var(--text-faint)', padding: 2 },
    }, Icon('x', 15)) : null);
}

/* ------------------------------------------------------------------ Drawer */
function Drawer({ open = true, title, eyebrow, subtitle, onClose, width = 520, footer, children, style = {} }) {
  React.useEffect(() => {
    if (!open || !onClose) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  return h('div', {
    style: { position: 'fixed', inset: 0, background: 'var(--scrim)', zIndex: 60, display: 'flex', justifyContent: 'flex-end' },
  },
    h('div', { onClick: onClose, style: { flex: 1 } }),
    h('div', {
      role: 'dialog', 'aria-modal': 'true',
      style: Object.assign({
        width, maxWidth: '92vw', height: '100%', background: 'var(--surface-card)', boxShadow: 'var(--shadow-lg)',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }, style),
    },
      h('div', {
        style: {
          display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, flex: 'none',
          padding: 22, borderBottom: '1px solid var(--border-subtle)',
        },
      },
        h('div', { style: { minWidth: 0 } },
          eyebrow ? h('div', { className: 'aegis-eyebrow' }, eyebrow) : null,
          h('h2', { style: { fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--text-strong)', marginTop: 4 } }, title),
          subtitle ? h('p', { style: { fontSize: 'var(--text-sm)', color: 'var(--text-muted)' } }, subtitle) : null),
        onClose && ns.IconButton ? h(ns.IconButton, { icon: 'x', label: 'Fechar', variant: 'ghost', onClick: onClose }) : null),
      h('div', { style: { flex: 1, overflowY: 'auto', padding: 22 } }, children),
      footer ? h('div', { style: { flex: 'none', padding: 22, borderTop: '1px solid var(--border-subtle)' } }, footer) : null));
}

/* ------------------------------------------------------------------- Chart */
const AXIS = { fontSize: 'var(--text-2xs)', color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' };

function DivergingChart({ data, height, posLabel, negLabel, posColor, negColor, onSelect }) {
  const max = Math.max(1, ...data.map((d) => Math.max(d.pos || 0, d.neg || 0)));
  const half = (height - 26) / 2;
  const [hi, setHi] = React.useState(-1);
  return h('div', null,
    h('div', { style: { display: 'flex', alignItems: 'center', gap: 16, marginBottom: 12 } },
      [[posLabel, posColor], [negLabel, negColor]].map(([l, c]) => h('span', {
        key: l, style: { display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 'var(--text-2xs)', fontWeight: 600, color: 'var(--text-muted)' },
      }, h('span', { style: { width: 9, height: 9, borderRadius: 2, background: c } }), l))),
    h('div', { style: { display: 'flex', alignItems: 'stretch', gap: 6, height } },
      data.map((d, i) => h('div', {
        key: d.label + i,
        onMouseEnter: () => setHi(i), onMouseLeave: () => setHi(-1),
        onClick: onSelect ? () => onSelect(d) : undefined,
        style: { flex: 1, display: 'flex', flexDirection: 'column', cursor: onSelect ? 'pointer' : 'default', opacity: hi === -1 || hi === i ? 1 : 0.55 },
      },
        h('div', { style: { height: half, display: 'flex', alignItems: 'flex-end' } },
          h('div', { title: `${d.pos} min excedentes`, style: { width: '100%', height: `${((d.pos || 0) / max) * 100}%`, background: posColor, borderRadius: '3px 3px 0 0', transition: 'height var(--duration-slow) var(--ease-out)' } })),
        h('div', { style: { height: 1, background: 'var(--border-default)' } }),
        h('div', { style: { height: half, display: 'flex', alignItems: 'flex-start' } },
          h('div', { title: `${d.neg} min faltantes`, style: { width: '100%', height: `${((d.neg || 0) / max) * 100}%`, background: negColor, borderRadius: '0 0 3px 3px', transition: 'height var(--duration-slow) var(--ease-out)' } })),
        h('div', { style: Object.assign({ textAlign: 'center', marginTop: 6, fontWeight: hi === i ? 700 : 400, color: hi === i ? 'var(--text-strong)' : 'var(--text-faint)' }, AXIS) }, d.label)))));
}

function TrendChart({ data, height, color, area = true, gridColor = 'var(--border-subtle)', labelColor = 'var(--text-faint)', labelSize }) {
  const w = 100;
  const max = Math.max(1, ...data.map((d) => d.value || 0));
  const step = data.length > 1 ? w / (data.length - 1) : w;
  const pts = data.map((d, i) => [i * step, 100 - ((d.value || 0) / max) * 88]);
  const line = pts.map((p) => `${p[0].toFixed(2)},${p[1].toFixed(2)}`).join(' ');
  const gid = React.useId().replace(/:/g, '');
  return h('div', null,
    h('div', { style: { position: 'relative', height } },
      h('svg', { viewBox: '0 0 100 100', preserveAspectRatio: 'none', style: { width: '100%', height: '100%', display: 'block', overflow: 'visible' } },
        h('defs', null, h('linearGradient', { id: gid, x1: '0', y1: '0', x2: '0', y2: '1' },
          h('stop', { offset: '0%', stopColor: color, stopOpacity: 0.24 }),
          h('stop', { offset: '100%', stopColor: color, stopOpacity: 0 }))),
        [25, 50, 75].map((y) => h('line', { key: y, x1: 0, x2: 100, y1: y, y2: y, stroke: gridColor, strokeWidth: 0.4, vectorEffect: 'non-scaling-stroke' })),
        area ? h('polygon', { points: `0,100 ${line} 100,100`, fill: `url(#${gid})` }) : null,
        h('polyline', { points: line, fill: 'none', stroke: color, strokeWidth: 2, vectorEffect: 'non-scaling-stroke', strokeLinejoin: 'round', strokeLinecap: 'round' }),
        pts.map((p, i) => h('circle', { key: i, cx: p[0], cy: p[1], r: 2.2, fill: 'var(--surface-card)', stroke: color, strokeWidth: 1.6, vectorEffect: 'non-scaling-stroke' })))),
    h('div', { style: { display: 'flex', justifyContent: 'space-between', marginTop: 8 } },
      data.map((d, i) => h('span', { key: i, style: Object.assign({}, AXIS, { color: labelColor }, labelSize ? { fontSize: labelSize } : null) }, d.label))));
}

function RankBarChart({ data, color, showValue = true, labelSize = 'var(--text-sm)', valueSize = 'var(--text-sm)', barHeight = 7, labelColor = 'var(--text-body)', valueColor = 'var(--text-strong)', track = 'rgba(17,29,45,0.07)', gap = 12 }) {
  const max = Math.max(1, ...data.map((d) => d.value || 0));
  return h('div', { style: { display: 'flex', flexDirection: 'column', gap } },
    data.map((d, i) => h('div', { key: d.label + i, style: { display: 'flex', flexDirection: 'column', gap: 5 } },
      h('div', { style: { display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 } },
        h('span', { style: { fontSize: labelSize, color: labelColor, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, d.label),
        showValue ? h('span', { className: 'aegis-tnum', style: { fontSize: valueSize, fontWeight: 700, color: valueColor, flex: 'none' } }, d.display ?? d.value) : null),
      h('div', { style: { height: barHeight, borderRadius: 'var(--radius-pill)', background: track, overflow: 'hidden' } },
        h('div', { style: { height: '100%', width: `${d.pct ?? ((d.value || 0) / max) * 100}%`, background: d.color || color, borderRadius: 'var(--radius-pill)', transition: 'width var(--duration-slow) var(--ease-out)' } })))));
}

/**
 * Chart — the three forms the product uses.
 * type: 'diverging' (zero in the middle: excedente above, faltante below)
 *     | 'trend'     (time series, optional area fill)
 *     | 'rankbar'   (horizontal ranking)
 * data: diverging [{label,pos,neg}] · trend [{label,value}] · rankbar [{label,value,display,pct}]
 */
function Chart({
  type = 'trend', data = [], height = 200, color = 'var(--brand)',
  posColor = 'var(--accent-violet)', negColor = 'var(--accent-orange)',
  posLabel = 'Excedente', negLabel = 'Faltante', empty, onSelect, style = {},
  gridColor, labelColor, labelSize, valueSize, barHeight, valueColor, track, gap,
}) {
  if (!data.length) {
    return h('div', { style: Object.assign({ height, display: 'flex', alignItems: 'center', justifyContent: 'center' }, style) },
      h('span', { style: { fontSize: 'var(--text-sm)', color: 'var(--text-faint)' } }, empty || 'Sem dado no período'));
  }
  const inner = type === 'diverging'
    ? h(DivergingChart, { data, height, posLabel, negLabel, posColor, negColor, onSelect })
    : type === 'rankbar'
      ? h(RankBarChart, { data, color, labelSize, valueSize, barHeight, labelColor, valueColor, track, gap })
      : h(TrendChart, { data, height, color, gridColor, labelColor, labelSize });
  return h('div', { style: Object.assign({ width: '100%' }, style) }, inner);
}

Object.assign(ns, { Table, Chart, Drawer, Tabs, EmptyState, Toast, Skeleton, Pagination });

if (typeof document !== 'undefined' && !document.getElementById('aegis-extras-kf')) {
  const st = document.createElement('style');
  st.id = 'aegis-extras-kf';
  st.textContent = '@keyframes aegis-skeleton{0%{background-position:100% 50%}100%{background-position:0 50%}}';
  document.head.appendChild(st);
}
})();
