/* @ds-bundle: {"format":3,"namespace":"AegisDesignSystem_86ea41","components":[{"name":"Avatar","sourcePath":"components/core/Avatar.jsx"},{"name":"Badge","sourcePath":"components/core/Badge.jsx"},{"name":"Button","sourcePath":"components/core/Button.jsx"},{"name":"Card","sourcePath":"components/core/Card.jsx"},{"name":"CardHeader","sourcePath":"components/core/Card.jsx"},{"name":"Icon","sourcePath":"components/core/Icon.jsx"},{"name":"IconButton","sourcePath":"components/core/IconButton.jsx"},{"name":"SegmentedControl","sourcePath":"components/core/SegmentedControl.jsx"},{"name":"ExposureCard","sourcePath":"components/data/ExposureCard.jsx"},{"name":"KpiCard","sourcePath":"components/data/KpiCard.jsx"},{"name":"Tooltip","sourcePath":"components/feedback/Tooltip.jsx"},{"name":"Checkbox","sourcePath":"components/forms/Checkbox.jsx"},{"name":"DateField","sourcePath":"components/forms/DateField.jsx"},{"name":"Input","sourcePath":"components/forms/Input.jsx"},{"name":"Select","sourcePath":"components/forms/Select.jsx"},{"name":"Switch","sourcePath":"components/forms/Switch.jsx"}],"sourceHashes":{"components/core/Avatar.jsx":"129a79833e3e","components/core/Badge.jsx":"715be2f21b3a","components/core/Button.jsx":"4c535840a3d9","components/core/Card.jsx":"b25acbabfd30","components/core/Icon.jsx":"cae1c81487dc","components/core/IconButton.jsx":"311d4fe4c5f7","components/core/SegmentedControl.jsx":"655c028ce795","components/data/ExposureCard.jsx":"f950c93a6a60","components/data/KpiCard.jsx":"6869048b258f","components/feedback/Tooltip.jsx":"00dc5dc6f432","components/forms/Checkbox.jsx":"2db9f24553be","components/forms/DateField.jsx":"adf5be4d5ddd","components/forms/Input.jsx":"1ad5d7ba6e64","components/forms/Select.jsx":"673490455999","components/forms/Switch.jsx":"4a4b7f0c2cc4","ui_kits/relatorios/Chrome.jsx":"f7af1c9ca97c","ui_kits/relatorios/Report.jsx":"5ef89f9ae0c3","ui_kits/relatorios/ReportMid.jsx":"5a648ff0bd5a","ui_kits/relatorios/ReportTech.jsx":"738ebe7d9ade","ui_kits/relatorios/ReportTop.jsx":"a40806d98341","ui_kits/relatorios/data.js":"4a836baa9c05","ui_kits/visao-executiva/ChartTooltip.jsx":"7afef2af27e6","ui_kits/visao-executiva/Charts.jsx":"50715391f7ba","ui_kits/visao-executiva/Dashboard.jsx":"8f1a18bf026d","ui_kits/visao-executiva/Drawer.jsx":"6a985713f527","ui_kits/visao-executiva/FilterBar.jsx":"fa32f20f0a43","ui_kits/visao-executiva/Header.jsx":"a3733707ed24","ui_kits/visao-executiva/OccurrencesTable.jsx":"612638c4e368","ui_kits/visao-executiva/Sidebar.jsx":"6434a2578317","ui_kits/visao-executiva/data.js":"125e416547a3"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.AegisDesignSystem_86ea41 = window.AegisDesignSystem_86ea41 || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/core/Avatar.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const sizes = {
  xs: 24,
  sm: 32,
  md: 40,
  lg: 48
};
function initials(name = '') {
  const p = name.trim().split(/\s+/);
  return ((p[0]?.[0] || '') + (p[1]?.[0] || '')).toUpperCase() || '?';
}

/** User avatar — image with initials fallback and optional status ring. */
function Avatar({
  name = '',
  src,
  size = 'md',
  status,
  className = '',
  style = {},
  ...rest
}) {
  const dim = sizes[size] || sizes.md;
  const [err, setErr] = React.useState(false);
  const statusColor = {
    online: 'var(--good-foreground)',
    busy: 'var(--bad-foreground)',
    away: 'var(--alert-foreground)'
  }[status];
  return /*#__PURE__*/React.createElement("span", _extends({
    className: `aegis-avatar ${className}`,
    style: {
      position: 'relative',
      display: 'inline-flex',
      flex: 'none',
      width: dim,
      height: dim,
      ...style
    }
  }, rest), src && !err ? /*#__PURE__*/React.createElement("img", {
    src: src,
    alt: name,
    onError: () => setErr(true),
    style: {
      width: '100%',
      height: '100%',
      borderRadius: '50%',
      objectFit: 'cover'
    }
  }) : /*#__PURE__*/React.createElement("span", {
    style: {
      width: '100%',
      height: '100%',
      borderRadius: '50%',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'linear-gradient(135deg, var(--categorical-7), #3D3D3D)',
      color: '#fff',
      fontSize: dim * 0.38,
      fontWeight: 'var(--weight-bold)',
      letterSpacing: 0
    }
  }, initials(name)), statusColor && /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'absolute',
      right: -1,
      bottom: -1,
      width: dim * 0.28,
      height: dim * 0.28,
      minWidth: 8,
      minHeight: 8,
      borderRadius: '50%',
      background: statusColor,
      border: '2px solid var(--surface-card)'
    }
  }));
}
Object.assign(__ds_scope, { Avatar });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Avatar.jsx", error: String((e && e.message) || e) }); }

// components/core/Badge.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const tones = {
  neutral: {
    bg: 'var(--surface-muted)',
    fg: 'var(--text-body)',
    dot: 'var(--foreground-quaternary)'
  },
  brand: {
    bg: 'var(--brand-soft)',
    fg: 'var(--brand-strong)',
    dot: 'var(--brand)'
  },
  bad: {
    bg: 'var(--bad-background)',
    fg: 'var(--bad-foreground)',
    dot: 'var(--bad-foreground)'
  },
  good: {
    bg: 'var(--good-background)',
    fg: 'var(--good-foreground)',
    dot: 'var(--good-foreground)'
  },
  alert: {
    bg: 'var(--alert-background)',
    fg: 'var(--alert-foreground)',
    dot: 'var(--alert-foreground)'
  }
};

/** Compact status / severity pill. */
function Badge({
  children,
  tone = 'neutral',
  dot = false,
  size = 'md',
  className = '',
  style = {},
  ...rest
}) {
  const t = tones[tone] || tones.neutral;
  const sm = size === 'sm';
  return /*#__PURE__*/React.createElement("span", _extends({
    className: `aegis-badge ${className}`,
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      height: sm ? 20 : 24,
      padding: sm ? '0 8px' : '0 10px',
      fontSize: sm ? 'var(--text-2xs)' : 'var(--text-xs)',
      fontWeight: 'var(--weight-semibold)',
      lineHeight: 1,
      whiteSpace: 'nowrap',
      color: t.fg,
      background: t.bg,
      borderRadius: 'var(--radius-pill)',
      ...style
    }
  }, rest), dot && /*#__PURE__*/React.createElement("span", {
    style: {
      width: 6,
      height: 6,
      borderRadius: '50%',
      background: t.dot,
      flex: 'none'
    }
  }), children);
}
Object.assign(__ds_scope, { Badge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Badge.jsx", error: String((e && e.message) || e) }); }

// components/core/Card.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const pads = {
  none: 0,
  sm: 'var(--space-4)',
  md: 'var(--space-5)',
  lg: 'var(--space-6)'
};

/** Rounded surface container — the base of every panel in Aegis. */
function Card({
  children,
  padding = 'md',
  interactive = false,
  className = '',
  style = {},
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("div", _extends({
    onMouseEnter: () => interactive && setHover(true),
    onMouseLeave: () => interactive && setHover(false),
    className: `aegis-card ${className}`,
    style: {
      background: 'var(--surface-card)',
      border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-xl)',
      boxShadow: hover ? 'var(--shadow-md)' : 'var(--shadow-sm)',
      padding: pads[padding] ?? pads.md,
      transition: 'box-shadow var(--duration-base) var(--ease-standard), transform var(--duration-base) var(--ease-standard)',
      transform: hover ? 'translateY(-1px)' : 'none',
      cursor: interactive ? 'pointer' : 'default',
      ...style
    }
  }, rest), children);
}

/** Card header row: title (+ optional eyebrow) on the left, actions on the right. */
function CardHeader({
  title,
  eyebrow,
  icon,
  actions,
  style = {}
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'flex-start',
      justifyContent: 'space-between',
      gap: 'var(--space-4)',
      marginBottom: 'var(--space-4)',
      ...style
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 'var(--space-3)',
      minWidth: 0
    }
  }, icon && /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 36,
      height: 36,
      borderRadius: 'var(--radius-lg)',
      background: 'var(--brand-soft)',
      color: 'var(--brand-strong)',
      flex: 'none'
    }
  }, icon), /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, eyebrow && /*#__PURE__*/React.createElement("div", {
    className: "aegis-eyebrow",
    style: {
      marginBottom: 2
    }
  }, eyebrow), /*#__PURE__*/React.createElement("h3", {
    style: {
      fontSize: 'var(--text-lg)',
      fontWeight: 'var(--weight-bold)',
      color: 'var(--text-strong)'
    }
  }, title))), actions && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 'var(--space-2)',
      flex: 'none'
    }
  }, actions));
}
Object.assign(__ds_scope, { Card, CardHeader });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Card.jsx", error: String((e && e.message) || e) }); }

// components/core/Icon.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Aegis linear icon. Renders a Lucide glyph. Requires the Lucide
 * UMD script to be present on the page (loaded via CDN in cards/kits).
 */
function Icon({
  name,
  size = 18,
  strokeWidth = 2,
  color,
  className = '',
  style = {},
  ...rest
}) {
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (typeof window !== 'undefined' && window.lucide && window.lucide.createIcons) {
      window.lucide.createIcons();
    }
  });
  return /*#__PURE__*/React.createElement("span", _extends({
    ref: ref,
    className: `aegis-icon ${className}`,
    style: {
      width: size,
      height: size,
      color,
      '--aegis-sw': strokeWidth,
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("i", {
    "data-lucide": name
  }));
}
Object.assign(__ds_scope, { Icon });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Icon.jsx", error: String((e && e.message) || e) }); }

// components/core/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const sizeMap = {
  sm: {
    height: 'var(--control-h-sm)',
    padding: '0 14px',
    font: 'var(--text-sm)',
    gap: 6,
    icon: 15
  },
  md: {
    height: 'var(--control-h-md)',
    padding: '0 18px',
    font: 'var(--text-base)',
    gap: 8,
    icon: 17
  },
  lg: {
    height: 'var(--control-h-lg)',
    padding: '0 24px',
    font: 'var(--text-md)',
    gap: 9,
    icon: 19
  }
};
const variants = {
  primary: {
    background: 'var(--brand)',
    color: 'var(--text-on-accent)',
    border: '1px solid transparent',
    boxShadow: 'var(--shadow-xs)',
    '--hov-bg': 'var(--brand-strong)',
    '--act-bg': 'var(--brand-strong)'
  },
  secondary: {
    background: 'var(--control-bg)',
    color: 'var(--text-strong)',
    border: '1px solid var(--control-border)',
    boxShadow: 'var(--shadow-xs)',
    '--hov-bg': 'var(--control-bg-hover)',
    '--act-bg': 'var(--control-bg-hover)'
  },
  ghost: {
    background: 'transparent',
    color: 'var(--text-body)',
    border: '1px solid transparent',
    '--hov-bg': 'var(--surface-muted)',
    '--act-bg': 'var(--surface-muted)'
  },
  danger: {
    background: 'var(--bad-foreground)',
    color: '#fff',
    border: '1px solid transparent',
    boxShadow: 'var(--shadow-xs)',
    '--hov-bg': 'var(--bad-foreground)',
    '--act-bg': 'var(--bad-foreground)'
  }
};

/** Pill-shaped action button. */
function Button({
  children,
  variant = 'primary',
  size = 'md',
  icon,
  iconRight,
  fullWidth = false,
  disabled = false,
  loading = false,
  className = '',
  style = {},
  ...rest
}) {
  const s = sizeMap[size] || sizeMap.md;
  const v = variants[variant] || variants.primary;
  const [hover, setHover] = React.useState(false);
  const [active, setActive] = React.useState(false);
  const bg = disabled ? 'var(--control-disabled-bg)' : active ? v['--act-bg'] : hover ? v['--hov-bg'] : v.background;
  return /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    disabled: disabled || loading,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => {
      setHover(false);
      setActive(false);
    },
    onMouseDown: () => setActive(true),
    onMouseUp: () => setActive(false),
    className: `aegis-btn ${className}`,
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      gap: s.gap,
      height: s.height,
      padding: s.padding,
      width: fullWidth ? '100%' : 'auto',
      fontFamily: 'var(--font-sans)',
      fontSize: s.font,
      fontWeight: 'var(--weight-semibold)',
      lineHeight: 1,
      letterSpacing: 'var(--tracking-normal)',
      whiteSpace: 'nowrap',
      borderRadius: 'var(--radius-pill)',
      background: bg,
      color: disabled ? 'var(--control-disabled-fg)' : v.color,
      border: v.border,
      boxShadow: disabled ? 'none' : v.boxShadow,
      cursor: disabled || loading ? 'not-allowed' : 'pointer',
      transform: active && !disabled ? 'translateY(0.5px)' : 'none',
      transition: 'var(--transition-control), transform var(--duration-fast) var(--ease-standard)',
      ...style
    }
  }, rest), loading && /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "loader-circle",
    size: s.icon,
    className: "aegis-spin"
  }), !loading && icon && /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: icon,
    size: s.icon
  }), children, !loading && iconRight && /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: iconRight,
    size: s.icon
  }));
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Button.jsx", error: String((e && e.message) || e) }); }

// components/core/IconButton.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const sizeMap = {
  sm: {
    box: 32,
    icon: 16
  },
  md: {
    box: 40,
    icon: 18
  },
  lg: {
    box: 44,
    icon: 20
  }
};

/** Circular icon-only button — header actions, table row actions. */
function IconButton({
  icon,
  label,
  variant = 'soft',
  size = 'md',
  badge,
  disabled = false,
  className = '',
  style = {},
  ...rest
}) {
  const s = sizeMap[size] || sizeMap.md;
  const [hover, setHover] = React.useState(false);
  const styles = {
    soft: {
      background: hover ? 'var(--control-bg-hover)' : 'var(--control-bg)',
      border: '1px solid var(--control-border)',
      color: 'var(--text-body)'
    },
    ghost: {
      background: hover ? 'var(--surface-muted)' : 'transparent',
      border: '1px solid transparent',
      color: 'var(--text-body)'
    },
    onDark: {
      background: hover ? 'rgba(255,255,255,0.16)' : 'rgba(255,255,255,0.08)',
      border: '1px solid rgba(255,255,255,0.10)',
      color: '#E7EDF5'
    },
    brand: {
      background: hover ? 'var(--brand-strong)' : 'var(--brand)',
      border: '1px solid transparent',
      color: '#fff'
    }
  };
  const v = styles[variant] || styles.soft;
  return /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    "aria-label": label,
    title: label,
    disabled: disabled,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    className: `aegis-iconbtn ${className}`,
    style: {
      position: 'relative',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: s.box,
      height: s.box,
      borderRadius: 'var(--radius-full)',
      cursor: disabled ? 'not-allowed' : 'pointer',
      flex: 'none',
      opacity: disabled ? 0.5 : 1,
      transition: 'var(--transition-control)',
      ...v,
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: icon,
    size: s.icon
  }), badge != null && /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'absolute',
      top: -2,
      right: -2,
      minWidth: 16,
      height: 16,
      padding: '0 4px',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontSize: 10,
      fontWeight: 'var(--weight-bold)',
      color: '#fff',
      background: 'var(--accent-orange)',
      borderRadius: 'var(--radius-pill)',
      border: '2px solid var(--surface-card)',
      lineHeight: 1
    }
  }, badge));
}
Object.assign(__ds_scope, { IconButton });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/IconButton.jsx", error: String((e && e.message) || e) }); }

// components/core/SegmentedControl.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Segmented control — period pickers (7d/15d/30d…) and table view toggles
 * (Todos / Alarmes / Anomalias).
 */
function SegmentedControl({
  options,
  value,
  onChange,
  size = 'md',
  className = '',
  style = {},
  ...rest
}) {
  const items = options.map(o => typeof o === 'string' ? {
    label: o,
    value: o
  } : o);
  const sm = size === 'sm';
  return /*#__PURE__*/React.createElement("div", _extends({
    role: "tablist",
    className: `aegis-segmented ${className}`,
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 2,
      padding: 3,
      background: 'var(--surface-muted)',
      borderRadius: 'var(--radius-pill)',
      border: '1px solid var(--border-subtle)',
      ...style
    }
  }, rest), items.map(it => {
    const selected = it.value === value;
    return /*#__PURE__*/React.createElement("button", {
      key: it.value,
      role: "tab",
      "aria-selected": selected,
      onClick: () => onChange && onChange(it.value),
      style: {
        appearance: 'none',
        border: 'none',
        cursor: 'pointer',
        height: sm ? 24 : 30,
        padding: sm ? '0 10px' : '0 14px',
        fontFamily: 'var(--font-sans)',
        fontSize: sm ? 'var(--text-xs)' : 'var(--text-sm)',
        fontWeight: 'var(--weight-semibold)',
        lineHeight: 1,
        borderRadius: 'var(--radius-pill)',
        whiteSpace: 'nowrap',
        color: selected ? 'var(--text-on-accent)' : 'var(--text-muted)',
        background: selected ? 'var(--brand)' : 'transparent',
        boxShadow: selected ? 'var(--shadow-xs)' : 'none',
        transition: 'var(--transition-control)'
      }
    }, it.label);
  }));
}
Object.assign(__ds_scope, { SegmentedControl });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/SegmentedControl.jsx", error: String((e && e.message) || e) }); }

// components/data/ExposureCard.jsx
try { (() => {
/** Exposure metric card: big hour figure + inline period selector. */
function ExposureCard({
  title,
  value,
  caption,
  icon = 'clock',
  periods = ['7d', '15d', '30d', '60d', '90d'],
  period = '30d',
  onPeriodChange,
  accent = 'violet',
  className = '',
  style = {}
}) {
  const a = {
    violet: {
      fg: 'var(--accent-violet)',
      bg: 'rgba(31,122,138,0.14)'
    },
    brand: {
      fg: 'var(--brand-strong)',
      bg: 'var(--brand-soft)'
    },
    amber: {
      fg: 'var(--accent-amber)',
      bg: 'var(--alert-background)'
    }
  }[accent] || {
    fg: 'var(--accent-violet)',
    bg: 'rgba(31,122,138,0.14)'
  };
  return /*#__PURE__*/React.createElement("div", {
    className: `aegis-exposure ${className}`,
    style: {
      background: 'var(--surface-card)',
      border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-xl)',
      padding: 'var(--space-5)',
      boxShadow: 'var(--shadow-sm)',
      display: 'flex',
      flexDirection: 'column',
      gap: 'var(--space-4)',
      ...style
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 38,
      height: 38,
      borderRadius: 'var(--radius-lg)',
      background: a.bg,
      color: a.fg
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: icon,
    size: 19
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-base)',
      fontWeight: 'var(--weight-semibold)',
      color: 'var(--text-strong)'
    }
  }, title)), /*#__PURE__*/React.createElement(__ds_scope.SegmentedControl, {
    options: periods,
    value: period,
    onChange: onPeriodChange,
    size: "sm"
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'baseline',
      gap: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "aegis-tnum",
    style: {
      fontSize: 'var(--text-4xl)',
      fontWeight: 'var(--weight-extra)',
      color: a.fg,
      lineHeight: 1,
      letterSpacing: 'var(--tracking-tight)'
    }
  }, value)), caption && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)'
    }
  }, caption));
}
Object.assign(__ds_scope, { ExposureCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/data/ExposureCard.jsx", error: String((e && e.message) || e) }); }

// components/data/KpiCard.jsx
try { (() => {
const accents = {
  brand: {
    fg: 'var(--brand-strong)',
    bg: 'var(--brand-soft)'
  },
  alert: {
    fg: 'var(--alert-foreground)',
    bg: 'var(--alert-background)'
  },
  bad: {
    fg: 'var(--bad-foreground)',
    bg: 'var(--bad-background)'
  },
  good: {
    fg: 'var(--good-foreground)',
    bg: 'var(--good-background)'
  },
  violet: {
    fg: 'var(--accent-violet)',
    bg: 'rgba(31,122,138,0.14)'
  }
};

/** KPI card: small title, big number, short caption, icon tile. */
function KpiCard({
  title,
  value,
  caption,
  icon = 'file-text',
  accent = 'brand',
  trend,
  className = '',
  style = {}
}) {
  const a = accents[accent] || accents.brand;
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("div", {
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    className: `aegis-kpi ${className}`,
    style: {
      background: 'var(--surface-card)',
      border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-xl)',
      padding: 'var(--space-5)',
      boxShadow: hover ? 'var(--shadow-md)' : 'var(--shadow-sm)',
      transform: hover ? 'translateY(-1px)' : 'none',
      transition: 'box-shadow var(--duration-base) var(--ease-standard), transform var(--duration-base) var(--ease-standard)',
      display: 'flex',
      flexDirection: 'column',
      gap: 'var(--space-4)',
      ...style
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'flex-start',
      justifyContent: 'space-between',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "aegis-eyebrow",
    style: {
      marginTop: 4
    }
  }, title), /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 40,
      height: 40,
      flex: 'none',
      borderRadius: 'var(--radius-lg)',
      background: a.bg,
      color: a.fg
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: icon,
    size: 20
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'flex-end',
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "aegis-tnum",
    style: {
      fontSize: 'var(--text-3xl)',
      fontWeight: 'var(--weight-extra)',
      color: 'var(--text-strong)',
      lineHeight: 1,
      letterSpacing: 'var(--tracking-tight)'
    }
  }, value), trend && /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 3,
      marginBottom: 4,
      fontSize: 'var(--text-xs)',
      fontWeight: 'var(--weight-semibold)',
      color: trend.dir === 'down' ? 'var(--good-foreground)' : 'var(--bad-foreground)'
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: trend.dir === 'down' ? 'trending-down' : 'trending-up',
    size: 14
  }), trend.value)), caption && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)'
    }
  }, caption));
}
Object.assign(__ds_scope, { KpiCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/data/KpiCard.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Tooltip.jsx
try { (() => {
/** Lightweight hover tooltip. Wraps its trigger children. */
function Tooltip({
  content,
  placement = 'top',
  children,
  style = {}
}) {
  const [show, setShow] = React.useState(false);
  const pos = {
    top: {
      bottom: '100%',
      left: '50%',
      transform: 'transl-x',
      mb: 8
    },
    bottom: {
      top: '100%',
      left: '50%',
      transform: 'transl-x',
      mt: 8
    },
    left: {
      right: '100%',
      top: '50%',
      transform: 'transl-y',
      mr: 8
    },
    right: {
      left: '100%',
      top: '50%',
      transform: 'transl-y',
      ml: 8
    }
  }[placement] || {};
  const transform = pos.transform === 'transl-x' ? 'translateX(-50%)' : 'translateY(-50%)';
  return /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'relative',
      display: 'inline-flex',
      ...style
    },
    onMouseEnter: () => setShow(true),
    onMouseLeave: () => setShow(false)
  }, children, show && /*#__PURE__*/React.createElement("span", {
    role: "tooltip",
    style: {
      position: 'absolute',
      zIndex: 60,
      whiteSpace: 'nowrap',
      pointerEvents: 'none',
      bottom: pos.bottom,
      top: pos.top,
      left: pos.left,
      right: pos.right,
      transform,
      marginBottom: pos.mb,
      marginTop: pos.mt,
      marginLeft: pos.ml,
      marginRight: pos.mr,
      background: 'var(--background-header)',
      color: '#F5F7FA',
      fontSize: 'var(--text-2xs)',
      fontWeight: 'var(--weight-medium)',
      padding: '6px 9px',
      borderRadius: 'var(--radius-sm)',
      boxShadow: 'var(--shadow-md)'
    }
  }, content));
}
Object.assign(__ds_scope, { Tooltip });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Tooltip.jsx", error: String((e && e.message) || e) }); }

// components/forms/Checkbox.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/** Checkbox with label. */
function Checkbox({
  checked = false,
  onChange,
  label,
  disabled = false,
  style = {},
  ...rest
}) {
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 9,
      cursor: disabled ? 'not-allowed' : 'pointer',
      opacity: disabled ? 0.55 : 1,
      userSelect: 'none',
      ...style
    }
  }, /*#__PURE__*/React.createElement("span", _extends({
    onClick: () => !disabled && onChange && onChange(!checked),
    style: {
      width: 18,
      height: 18,
      flex: 'none',
      borderRadius: 'var(--radius-xs)',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: checked ? 'var(--brand)' : 'var(--control-bg)',
      border: `1px solid ${checked ? 'var(--brand)' : 'var(--control-border)'}`,
      transition: 'var(--transition-control)'
    }
  }, rest), checked && /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "check",
    size: 13,
    color: "var(--text-on-accent)",
    strokeWidth: 3
  })), label && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-body)'
    }
  }, label));
}
Object.assign(__ds_scope, { Checkbox });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Checkbox.jsx", error: String((e && e.message) || e) }); }

// components/forms/DateField.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/** Date field — a styled native date input with a calendar affordance. */
function DateField({
  label,
  value,
  onChange,
  size = 'md',
  disabled = false,
  className = '',
  style = {},
  wrapStyle = {},
  ...rest
}) {
  const h = size === 'sm' ? 'var(--control-h-sm)' : size === 'lg' ? 'var(--control-h-lg)' : 'var(--control-h-md)';
  const [focus, setFocus] = React.useState(false);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
      ...wrapStyle
    }
  }, label && /*#__PURE__*/React.createElement("label", {
    style: {
      fontSize: 'var(--text-xs)',
      fontWeight: 'var(--weight-semibold)',
      color: 'var(--text-muted)'
    }
  }, label), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative',
      display: 'flex',
      alignItems: 'center',
      height: h,
      padding: '0 12px',
      gap: 8,
      background: disabled ? 'var(--control-disabled-bg)' : 'var(--control-bg)',
      border: `1px solid ${focus ? 'var(--border-focus)' : 'var(--control-border)'}`,
      borderRadius: 'var(--radius-md)',
      boxShadow: focus ? 'var(--shadow-focus)' : 'none',
      transition: 'var(--transition-control)'
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "calendar",
    size: 16,
    color: "var(--text-faint)"
  }), /*#__PURE__*/React.createElement("input", _extends({
    type: "date",
    value: value,
    disabled: disabled,
    onChange: e => onChange && onChange(e.target.value),
    onFocus: () => setFocus(true),
    onBlur: () => setFocus(false),
    className: `aegis-datefield ${className}`,
    style: {
      flex: 1,
      minWidth: 0,
      border: 'none',
      outline: 'none',
      background: 'transparent',
      fontFamily: 'var(--font-sans)',
      fontSize: 'var(--text-base)',
      color: value ? 'var(--text-strong)' : 'var(--text-faint)',
      colorScheme: 'inherit',
      ...style
    }
  }, rest))));
}
Object.assign(__ds_scope, { DateField });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/DateField.jsx", error: String((e && e.message) || e) }); }

// components/forms/Input.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/** Labelled text field with optional leading icon. */
function Input({
  label,
  hint,
  icon,
  error,
  size = 'md',
  id,
  className = '',
  style = {},
  wrapStyle = {},
  ...rest
}) {
  const autoId = React.useId();
  const fieldId = id || autoId;
  const h = size === 'sm' ? 'var(--control-h-sm)' : size === 'lg' ? 'var(--control-h-lg)' : 'var(--control-h-md)';
  const [focus, setFocus] = React.useState(false);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
      ...wrapStyle
    }
  }, label && /*#__PURE__*/React.createElement("label", {
    htmlFor: fieldId,
    style: {
      fontSize: 'var(--text-xs)',
      fontWeight: 'var(--weight-semibold)',
      color: 'var(--text-muted)'
    }
  }, label), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      height: h,
      padding: '0 12px',
      background: rest.disabled ? 'var(--control-disabled-bg)' : 'var(--control-bg)',
      border: `1px solid ${error ? 'var(--bad-foreground)' : focus ? 'var(--border-focus)' : 'var(--control-border)'}`,
      borderRadius: 'var(--radius-md)',
      boxShadow: focus ? 'var(--shadow-focus)' : 'none',
      transition: 'var(--transition-control)'
    }
  }, icon && /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-faint)',
      display: 'inline-flex'
    }
  }, icon), /*#__PURE__*/React.createElement("input", _extends({
    id: fieldId,
    onFocus: e => {
      setFocus(true);
      rest.onFocus?.(e);
    },
    onBlur: e => {
      setFocus(false);
      rest.onBlur?.(e);
    },
    className: className,
    style: {
      flex: 1,
      minWidth: 0,
      border: 'none',
      outline: 'none',
      background: 'transparent',
      fontFamily: 'var(--font-sans)',
      fontSize: 'var(--text-base)',
      color: 'var(--text-strong)',
      ...style
    }
  }, rest))), (hint || error) && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-2xs)',
      color: error ? 'var(--bad-foreground)' : 'var(--text-faint)'
    }
  }, error || hint));
}
Object.assign(__ds_scope, { Input });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Input.jsx", error: String((e && e.message) || e) }); }

// components/forms/Select.jsx
try { (() => {
/**
 * Dropdown select with a label above. Pill or soft-rounded trigger.
 * Used throughout the filter bar.
 */
function Select({
  label,
  value,
  onChange,
  options = [],
  placeholder = 'Selecionar',
  size = 'md',
  shape = 'rounded',
  icon,
  disabled = false,
  fullWidth = true,
  className = '',
  style = {},
  wrapStyle = {}
}) {
  const items = options.map(o => typeof o === 'string' ? {
    label: o,
    value: o
  } : o);
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef(null);
  const selected = items.find(i => i.value === value);
  React.useEffect(() => {
    function onDoc(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);
  const h = size === 'sm' ? 'var(--control-h-sm)' : size === 'lg' ? 'var(--control-h-lg)' : 'var(--control-h-md)';
  const radius = shape === 'pill' ? 'var(--radius-pill)' : 'var(--radius-md)';
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
      width: fullWidth ? '100%' : 'auto',
      ...wrapStyle
    }
  }, label && /*#__PURE__*/React.createElement("label", {
    style: {
      fontSize: 'var(--text-xs)',
      fontWeight: 'var(--weight-semibold)',
      color: 'var(--text-muted)'
    }
  }, label), /*#__PURE__*/React.createElement("div", {
    ref: ref,
    style: {
      position: 'relative'
    },
    className: className
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    disabled: disabled,
    onClick: () => setOpen(o => !o),
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      width: '100%',
      height: h,
      padding: shape === 'pill' ? '0 14px' : '0 12px',
      background: disabled ? 'var(--control-disabled-bg)' : 'var(--control-bg)',
      color: disabled ? 'var(--control-disabled-fg)' : selected ? 'var(--text-strong)' : 'var(--text-faint)',
      border: `1px solid ${open ? 'var(--border-focus)' : 'var(--control-border)'}`,
      borderRadius: radius,
      cursor: disabled ? 'not-allowed' : 'pointer',
      fontFamily: 'var(--font-sans)',
      fontSize: 'var(--text-base)',
      fontWeight: 'var(--weight-medium)',
      boxShadow: open ? 'var(--shadow-focus)' : 'none',
      transition: 'var(--transition-control)',
      ...style
    }
  }, icon && /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-faint)',
      display: 'inline-flex'
    }
  }, icon), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      textAlign: 'left',
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap'
    }
  }, selected ? selected.label : placeholder), /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "chevron-down",
    size: 16,
    color: "var(--text-faint)",
    style: {
      transform: open ? 'rotate(180deg)' : 'none',
      transition: 'transform var(--duration-fast)'
    }
  })), open && /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      top: 'calc(100% + 6px)',
      left: 0,
      right: 0,
      zIndex: 40,
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--radius-md)',
      boxShadow: 'var(--shadow-lg)',
      padding: 4,
      maxHeight: 260,
      overflowY: 'auto'
    }
  }, items.map(it => {
    const isSel = it.value === value;
    return /*#__PURE__*/React.createElement("button", {
      key: it.value,
      type: "button",
      onClick: () => {
        onChange && onChange(it.value);
        setOpen(false);
      },
      style: {
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 8,
        width: '100%',
        padding: '8px 10px',
        border: 'none',
        cursor: 'pointer',
        background: isSel ? 'var(--brand-soft)' : 'transparent',
        color: isSel ? 'var(--brand-strong)' : 'var(--text-body)',
        borderRadius: 'var(--radius-sm)',
        textAlign: 'left',
        fontFamily: 'var(--font-sans)',
        fontSize: 'var(--text-sm)',
        fontWeight: isSel ? 'var(--weight-semibold)' : 'var(--weight-medium)'
      },
      onMouseEnter: e => {
        if (!isSel) e.currentTarget.style.background = 'var(--surface-muted)';
      },
      onMouseLeave: e => {
        if (!isSel) e.currentTarget.style.background = 'transparent';
      }
    }, it.label, isSel && /*#__PURE__*/React.createElement(__ds_scope.Icon, {
      name: "check",
      size: 15
    }));
  }))));
}
Object.assign(__ds_scope, { Select });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Select.jsx", error: String((e && e.message) || e) }); }

// components/forms/Switch.jsx
try { (() => {
/** Toggle switch — e.g. theme, real-time updates, group-by toggles. */
function Switch({
  checked = false,
  onChange,
  label,
  disabled = false,
  size = 'md',
  style = {}
}) {
  const w = size === 'sm' ? 34 : 42;
  const h = size === 'sm' ? 20 : 24;
  const knob = h - 6;
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 10,
      cursor: disabled ? 'not-allowed' : 'pointer',
      opacity: disabled ? 0.55 : 1,
      ...style
    }
  }, /*#__PURE__*/React.createElement("span", {
    role: "switch",
    "aria-checked": checked,
    onClick: () => !disabled && onChange && onChange(!checked),
    style: {
      position: 'relative',
      width: w,
      height: h,
      flex: 'none',
      borderRadius: 'var(--radius-pill)',
      background: checked ? 'var(--brand)' : 'var(--control-border)',
      transition: 'background-color var(--duration-base) var(--ease-standard)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'absolute',
      top: 3,
      left: checked ? w - knob - 3 : 3,
      width: knob,
      height: knob,
      borderRadius: '50%',
      background: '#fff',
      boxShadow: 'var(--shadow-sm)',
      transition: 'left var(--duration-base) var(--ease-out)'
    }
  })), label && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-body)'
    }
  }, label));
}
Object.assign(__ds_scope, { Switch });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Switch.jsx", error: String((e && e.message) || e) }); }

// ui_kits/relatorios/Chrome.jsx
try { (() => {
/* Relatórios — shared chrome: header, action bar, filters, panel helpers */
const RC = window.AegisDesignSystem_86ea41;

/* ---- shared panel primitives (same language as Visão Executiva) ---- */
function PanelCard({
  children,
  style,
  id
}) {
  return /*#__PURE__*/React.createElement("div", {
    id: id,
    style: {
      background: 'var(--surface-card)',
      border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-xl)',
      boxShadow: 'var(--shadow-sm)',
      padding: 'var(--space-5)',
      ...style
    }
  }, children);
}
const PANEL_TONES = {
  brand: ['var(--brand-soft)', 'var(--brand-strong)'],
  violet: ['rgba(31,122,138,0.14)', 'var(--accent-violet)'],
  amber: ['var(--alert-background)', 'var(--alert-foreground)'],
  heat: ['rgba(255,140,0,0.14)', 'var(--brand-strong)'],
  good: ['var(--good-background)', 'var(--good-foreground)'],
  bad: ['var(--bad-background)', 'var(--bad-foreground)']
};
function PanelHead({
  icon,
  iconTone,
  eyebrow,
  title,
  subtitle,
  right
}) {
  const tones = PANEL_TONES[iconTone] || PANEL_TONES.brand;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'flex-start',
      justifyContent: 'space-between',
      gap: 16,
      marginBottom: 20,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      minWidth: 0
    }
  }, icon && /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 38,
      height: 38,
      flex: 'none',
      borderRadius: 'var(--radius-lg)',
      background: tones[0],
      color: tones[1]
    }
  }, /*#__PURE__*/React.createElement(RC.Icon, {
    name: icon,
    size: 19
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, eyebrow && /*#__PURE__*/React.createElement("div", {
    className: "aegis-eyebrow",
    style: {
      marginBottom: 3
    }
  }, eyebrow), /*#__PURE__*/React.createElement("h3", {
    style: {
      fontSize: 'var(--text-lg)',
      fontWeight: 700,
      color: 'var(--text-strong)',
      lineHeight: 1.2
    }
  }, title), subtitle && /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)',
      marginTop: 3,
      maxWidth: 640
    }
  }, subtitle))), right && /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 'none'
    }
  }, right));
}

/* Section number eyebrow chip, e.g. "01" */
function SectionTag({
  n
}) {
  return /*#__PURE__*/React.createElement("span", {
    className: "aegis-mono",
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      minWidth: 30,
      height: 22,
      padding: '0 8px',
      borderRadius: 'var(--radius-pill)',
      background: 'var(--surface-muted)',
      color: 'var(--text-muted)',
      fontSize: 11,
      fontWeight: 700,
      letterSpacing: '0.04em'
    }
  }, n);
}

/* ---- status mapping ---- */
const STATUS_TONE = {
  'Normal': 'good',
  'Atenção': 'alert',
  'Ação Imediata': 'bad',
  'Crítico': 'bad',
  'Planejado': 'brand',
  'Aberto': 'alert'
};
const STATUS_ICON = {
  'Normal': 'check-circle-2',
  'Atenção': 'alert-triangle',
  'Ação Imediata': 'octagon-alert',
  'Crítico': 'flame'
};
const CRIT_TONE = {
  'Baixa': 'good',
  'Média': 'alert',
  'Alta': 'bad'
};
const CRIT_DOT = {
  'Baixa': 'var(--good-foreground)',
  'Média': 'var(--alert-foreground)',
  'Alta': 'var(--bad-foreground)'
};
const CELL_COLOR = {
  'Normal': ['var(--good-background)', 'var(--good-foreground)'],
  'Atenção': ['var(--alert-background)', 'var(--alert-foreground)'],
  'Ação Imediata': ['var(--bad-background)', 'var(--bad-foreground)']
};
window.REL_MAPS = {
  STATUS_TONE,
  STATUS_ICON,
  CRIT_TONE,
  CRIT_DOT,
  CELL_COLOR
};

/* Legend row: Normal / Atenção / Ação Imediata */
function StatusLegend({
  items
}) {
  const list = items || [['Normal', 'var(--good-foreground)'], ['Atenção', 'var(--alert-foreground)'], ['Ação Imediata', 'var(--bad-foreground)']];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 16,
      flexWrap: 'wrap'
    }
  }, list.map(([l, c]) => /*#__PURE__*/React.createElement("span", {
    key: l,
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 7,
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)',
      fontWeight: 500
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 11,
      height: 11,
      borderRadius: 3,
      background: c,
      flex: 'none'
    }
  }), " ", l)));
}

/* ===================== Header ===================== */
function ReportHeader({
  dark,
  onToggleTheme,
  user,
  tenant,
  onTenantClick
}) {
  return /*#__PURE__*/React.createElement("header", {
    "data-print-hide": true,
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 20,
      padding: '20px 28px',
      minHeight: 'var(--header-height)',
      flex: 'none',
      background: 'var(--surface-card)',
      borderBottom: '1px solid var(--border-subtle)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 14,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 44,
      height: 44,
      flex: 'none',
      borderRadius: 'var(--radius-lg)',
      background: 'var(--brand-soft)',
      color: 'var(--brand-strong)'
    }
  }, /*#__PURE__*/React.createElement(RC.Icon, {
    name: "file-bar-chart-2",
    size: 22
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      fontSize: 'var(--text-2xl)',
      fontWeight: 800,
      color: 'var(--text-strong)',
      lineHeight: 1.1
    }
  }, "Relat\xF3rios"), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-muted)',
      marginTop: 2
    }
  }, "Relat\xF3rios t\xE9cnicos e executivos de sa\xFAde dos sistemas"))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("button", {
    onClick: onTenantClick,
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 7,
      padding: '6px 12px 6px 6px',
      background: 'var(--surface-muted)',
      border: 'none',
      cursor: 'pointer',
      borderRadius: 'var(--radius-pill)',
      marginRight: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 26,
      height: 26,
      borderRadius: '50%',
      background: 'var(--brand)',
      color: '#fff',
      fontSize: 11,
      fontWeight: 700
    }
  }, tenant.name[0]), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-xs)',
      fontWeight: 600,
      color: 'var(--text-body)'
    }
  }, tenant.name), /*#__PURE__*/React.createElement(RC.Icon, {
    name: "chevrons-up-down",
    size: 14,
    color: "var(--text-faint)"
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 7,
      padding: '0 8px',
      borderRight: '1px solid var(--border-subtle)',
      marginRight: 4
    }
  }, /*#__PURE__*/React.createElement(RC.Icon, {
    name: dark ? 'moon' : 'sun',
    size: 16,
    color: "var(--text-faint)"
  }), /*#__PURE__*/React.createElement(RC.Switch, {
    checked: dark,
    onChange: onToggleTheme,
    size: "sm"
  })), /*#__PURE__*/React.createElement(RC.IconButton, {
    icon: "search",
    label: "Buscar"
  }), /*#__PURE__*/React.createElement(RC.IconButton, {
    icon: "mail",
    label: "Mensagens",
    badge: 2
  }), /*#__PURE__*/React.createElement(RC.IconButton, {
    icon: "bell",
    label: "Notifica\xE7\xF5es",
    badge: 5
  }), /*#__PURE__*/React.createElement(RC.Avatar, {
    name: user.name,
    size: "md",
    status: "online",
    style: {
      marginLeft: 4
    }
  })));
}

/* ===================== Action bar ===================== */
function ActionsBar({
  onPrint,
  onExportPdf,
  onExportXls,
  onRefresh,
  pdfLoading,
  refreshing
}) {
  return /*#__PURE__*/React.createElement("div", {
    "data-print-hide": true,
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 14,
      flexWrap: 'wrap',
      background: 'var(--surface-card)',
      border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-xl)',
      boxShadow: 'var(--shadow-sm)',
      padding: '14px 18px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 11,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 34,
      height: 34,
      borderRadius: 'var(--radius-md)',
      background: 'var(--brand-soft)',
      color: 'var(--brand-strong)',
      flex: 'none'
    }
  }, /*#__PURE__*/React.createElement(RC.Icon, {
    name: "file-text",
    size: 17
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-sm)',
      fontWeight: 700,
      color: 'var(--text-strong)'
    }
  }, "Relat\xF3rio de Sa\xFAde dos Sistemas"), /*#__PURE__*/React.createElement("div", {
    className: "aegis-mono",
    style: {
      fontSize: 'var(--text-2xs)',
      color: 'var(--text-muted)',
      marginTop: 1
    }
  }, "REL-2026-02-0184 \xB7 v2.1 \xB7 Fevereiro de 2026"))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 9,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement(RC.Button, {
    variant: "secondary",
    size: "sm",
    icon: "refresh-cw",
    loading: refreshing,
    onClick: onRefresh
  }, refreshing ? 'Atualizando…' : 'Atualizar'), /*#__PURE__*/React.createElement(RC.Button, {
    variant: "secondary",
    size: "sm",
    icon: "table",
    onClick: onExportXls
  }, "Exportar XLS"), /*#__PURE__*/React.createElement(RC.Button, {
    variant: "secondary",
    size: "sm",
    icon: "printer",
    onClick: onPrint
  }, "Imprimir"), /*#__PURE__*/React.createElement(RC.Button, {
    variant: "primary",
    size: "sm",
    icon: "file-down",
    loading: pdfLoading,
    onClick: onExportPdf
  }, pdfLoading ? 'Gerando…' : 'Exportar PDF')));
}

/* ===================== Filters ===================== */
function FilterChip({
  label,
  value,
  onRemove
}) {
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 7,
      padding: '5px 6px 5px 11px',
      borderRadius: 'var(--radius-pill)',
      background: 'var(--brand-soft)',
      border: '1px solid var(--border-subtle)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-2xs)',
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.04em',
      color: 'var(--brand-strong)'
    }
  }, label), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-xs)',
      fontWeight: 600,
      color: 'var(--text-strong)'
    }
  }, value), /*#__PURE__*/React.createElement("button", {
    onClick: onRemove,
    style: {
      display: 'inline-flex',
      width: 18,
      height: 18,
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: '50%',
      border: 'none',
      background: 'rgba(17,29,45,0.06)',
      cursor: 'pointer',
      color: 'var(--text-muted)'
    }
  }, /*#__PURE__*/React.createElement(RC.Icon, {
    name: "x",
    size: 12
  })));
}
function ReportFilters({
  data
}) {
  const [expanded, setExpanded] = React.useState(false);
  const [client, setClient] = React.useState('hersil');
  const [site, setSite] = React.useState('sptower');
  const [mes, setMes] = React.useState('2026-02');
  const [d1, setD1] = React.useState('2026-02-01');
  const [d2, setD2] = React.useState('2026-02-28');
  const [statusSys, setStatusSys] = React.useState('todos');
  const toOpts = arr => arr.map(x => ({
    label: x,
    value: x.toLowerCase()
  }));
  const [chips, setChips] = React.useState([{
    id: 'cli',
    label: 'Cliente',
    value: 'Hersil'
  }, {
    id: 'site',
    label: 'Site',
    value: 'SP Tower'
  }, {
    id: 'mes',
    label: 'Mês',
    value: 'Fev/2026'
  }, {
    id: 'st',
    label: 'Status',
    value: 'Todos'
  }]);
  const removeChip = id => setChips(c => c.filter(x => x.id !== id));
  return /*#__PURE__*/React.createElement("div", {
    "data-print-hide": true,
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      background: 'var(--surface-card)',
      border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-xl)',
      boxShadow: 'var(--shadow-sm)',
      padding: 'var(--space-5)',
      display: 'flex',
      flexDirection: 'column',
      gap: 18
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'flex-end',
      gap: 12,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 9,
      height: 'var(--control-h-md)',
      paddingRight: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 34,
      height: 34,
      borderRadius: 'var(--radius-md)',
      background: 'var(--brand-soft)',
      color: 'var(--brand-strong)'
    }
  }, /*#__PURE__*/React.createElement(RC.Icon, {
    name: "sliders-horizontal",
    size: 17
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-base)',
      fontWeight: 700,
      color: 'var(--text-strong)'
    }
  }, "Filtros")), /*#__PURE__*/React.createElement(RC.Select, {
    label: "Cliente",
    value: client,
    onChange: setClient,
    options: data.clients,
    wrapStyle: {
      width: 200
    },
    icon: /*#__PURE__*/React.createElement(RC.Icon, {
      name: "building-2",
      size: 15
    })
  }), /*#__PURE__*/React.createElement(RC.Select, {
    label: "Site / Unidade",
    value: site,
    onChange: setSite,
    options: data.sites,
    wrapStyle: {
      width: 220
    }
  }), /*#__PURE__*/React.createElement(RC.Select, {
    label: "M\xEAs de refer\xEAncia",
    value: mes,
    onChange: setMes,
    options: data.meses,
    wrapStyle: {
      width: 180
    },
    icon: /*#__PURE__*/React.createElement(RC.Icon, {
      name: "calendar",
      size: 15
    })
  }), /*#__PURE__*/React.createElement(RC.Button, {
    variant: "secondary",
    icon: "plus",
    iconRight: expanded ? 'chevron-up' : 'chevron-down',
    onClick: () => setExpanded(e => !e)
  }, "Mais filtros"), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement(RC.Button, {
    variant: "ghost",
    icon: "eraser",
    onClick: () => setChips([])
  }, "Limpar"), /*#__PURE__*/React.createElement(RC.Button, {
    variant: "primary",
    icon: "check"
  }, "Aplicar")), expanded && /*#__PURE__*/React.createElement("div", {
    style: {
      height: 1,
      background: 'var(--border-subtle)'
    }
  }), expanded && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(4, 1fr)',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement(RC.DateField, {
    label: "Data in\xEDcio",
    value: d1,
    onChange: setD1
  }), /*#__PURE__*/React.createElement(RC.DateField, {
    label: "Data fim",
    value: d2,
    onChange: setD2
  }), /*#__PURE__*/React.createElement(RC.Select, {
    label: "Gestor",
    options: toOpts(data.gestores),
    value: "todos"
  }), /*#__PURE__*/React.createElement(RC.Select, {
    label: "Especialista",
    options: toOpts(data.especialistas),
    value: "todos"
  })), expanded && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(4, 1fr)',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement(RC.Select, {
    label: "Sistema",
    options: toOpts(data.sistemasOpt),
    value: "todos os sistemas"
  }), /*#__PURE__*/React.createElement(RC.Select, {
    label: "Status do sistema",
    options: toOpts(data.statusSistema),
    value: statusSys,
    onChange: setStatusSys
  }), /*#__PURE__*/React.createElement(RC.Select, {
    label: "Condi\xE7\xE3o",
    options: toOpts(data.condicaoOpt),
    value: "todas"
  }), /*#__PURE__*/React.createElement(RC.Select, {
    label: "Criticidade",
    options: toOpts(data.criticidadeOpt),
    value: "todas"
  })), expanded && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(4, 1fr)',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement(RC.Select, {
    label: "Tipo de ocorr\xEAncia",
    options: toOpts(data.tipoOcorrencia),
    value: "todos"
  }), /*#__PURE__*/React.createElement(RC.Input, {
    label: "C\xF3digo do alarme / anomalia",
    placeholder: "Ex.: CH-04, 13",
    wrapStyle: {
      gridColumn: 'span 1'
    }
  }))), chips.length > 0 && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 9,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-2xs)',
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.06em',
      color: 'var(--text-faint)'
    }
  }, "Filtros aplicados"), chips.map(c => /*#__PURE__*/React.createElement(FilterChip, {
    key: c.id,
    label: c.label,
    value: c.value,
    onRemove: () => removeChip(c.id)
  })), /*#__PURE__*/React.createElement("button", {
    onClick: () => setChips([]),
    style: {
      fontSize: 'var(--text-xs)',
      fontWeight: 600,
      color: 'var(--brand-strong)',
      background: 'none',
      border: 'none',
      cursor: 'pointer'
    }
  }, "Limpar tudo")));
}
Object.assign(window, {
  PanelCard,
  PanelHead,
  SectionTag,
  StatusLegend,
  ReportHeader,
  ActionsBar,
  ReportFilters
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/relatorios/Chrome.jsx", error: String((e && e.message) || e) }); }

// ui_kits/relatorios/Report.jsx
try { (() => {
/* Relatórios — main composition */
const RP = window.AegisDesignSystem_86ea41;
function Toasts({
  toasts
}) {
  const tone = {
    info: ['var(--brand-soft)', 'var(--brand-strong)', 'loader'],
    success: ['var(--good-background)', 'var(--good-foreground)', 'check-circle-2'],
    error: ['var(--bad-background)', 'var(--bad-foreground)', 'x-circle']
  };
  return /*#__PURE__*/React.createElement("div", {
    "data-print-hide": true,
    style: {
      position: 'fixed',
      right: 22,
      bottom: 22,
      zIndex: 200,
      display: 'flex',
      flexDirection: 'column',
      gap: 10
    }
  }, toasts.map(t => {
    const [bg, fg, ic] = tone[t.kind] || tone.info;
    return /*#__PURE__*/React.createElement("div", {
      key: t.id,
      className: "rel-toast",
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: 11,
        padding: '13px 16px',
        minWidth: 280,
        maxWidth: 380,
        background: 'var(--surface-card)',
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-lg)'
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 32,
        height: 32,
        flex: 'none',
        borderRadius: 'var(--radius-md)',
        background: bg,
        color: fg
      }
    }, /*#__PURE__*/React.createElement(RP.Icon, {
      name: ic,
      size: 17,
      className: t.kind === 'info' ? 'rel-spin' : ''
    })), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 'var(--text-sm)',
        fontWeight: 600,
        color: 'var(--text-strong)'
      }
    }, t.msg));
  }));
}
function Report({
  onNavigate: extNav
} = {}) {
  const D = window.AEGIS_REPORT;
  const [dark, setDark] = React.useState(() => {
    try {
      return localStorage.getItem('aegis-theme') === 'dark';
    } catch (e) {
      return false;
    }
  });
  const [collapsed, setCollapsed] = React.useState(false);
  const [pdfLoading, setPdfLoading] = React.useState(false);
  const [refreshing, setRefreshing] = React.useState(false);
  const [annexOpen, setAnnexOpen] = React.useState(true);
  const [toasts, setToasts] = React.useState([]);
  React.useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
    try {
      localStorage.setItem('aegis-theme', dark ? 'dark' : 'light');
    } catch (e) {}
  }, [dark]);
  React.useEffect(() => {
    if (window.lucide) window.lucide.createIcons();
  });
  const pushToast = (msg, kind = 'info', ms = 2600) => {
    const id = Date.now() + Math.random();
    setToasts(t => [...t, {
      id,
      msg,
      kind
    }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), ms);
  };
  const onPrint = () => window.print();
  const onExportPdf = () => {
    setPdfLoading(true);
    pushToast('Gerando PDF do relatório…', 'info', 1800);
    setTimeout(() => {
      setPdfLoading(false);
      pushToast('PDF gerado com sucesso.', 'success');
    }, 1900);
  };
  const onExportXls = () => pushToast('Exportando dados em XLS…', 'info', 1400);
  const onRefresh = () => {
    setRefreshing(true);
    setTimeout(() => {
      setRefreshing(false);
      pushToast('Dados atualizados.', 'success');
    }, 1300);
  };
  const onNavigate = id => {
    if (id === 'exec') {
      if (extNav) extNav('exec');else window.location.href = '../visao-executiva/index.html';
    } else if (id !== 'reports') pushToast('Seção disponível na navegação completa do SaaS.', 'info', 1600);
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      height: '100vh',
      overflow: 'hidden',
      background: 'var(--surface-app)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    "data-print-hide": true,
    style: {
      display: 'flex',
      flex: 'none'
    }
  }, /*#__PURE__*/React.createElement(window.Sidebar, {
    active: "reports",
    onNavigate: onNavigate,
    collapsed: collapsed,
    onToggle: () => setCollapsed(c => !c),
    user: D.user
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0,
      height: '100vh',
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement(window.ReportHeader, {
    dark: dark,
    onToggleTheme: setDark,
    user: D.user,
    tenant: D.tenant,
    onTenantClick: () => pushToast('Troca de cliente disponível para administradores.', 'info', 1800)
  }), /*#__PURE__*/React.createElement("main", {
    id: "rel-scroll",
    style: {
      flex: 1,
      minHeight: 0,
      overflowY: 'auto',
      overflowX: 'hidden',
      padding: '24px 28px',
      display: 'flex',
      flexDirection: 'column',
      gap: 18
    }
  }, /*#__PURE__*/React.createElement(window.ActionsBar, {
    onPrint: onPrint,
    onExportPdf: onExportPdf,
    onExportXls: onExportXls,
    onRefresh: onRefresh,
    pdfLoading: pdfLoading,
    refreshing: refreshing
  }), /*#__PURE__*/React.createElement(window.ReportFilters, {
    data: D
  }), /*#__PURE__*/React.createElement("div", {
    id: "rel-doc",
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 18
    }
  }, /*#__PURE__*/React.createElement(window.ReportCover, {
    cover: D.cover
  }), /*#__PURE__*/React.createElement(window.TeamSection, {
    team: D.team
  }), /*#__PURE__*/React.createElement(window.ConditionSection, {
    items: D.condicaoGeral
  }), /*#__PURE__*/React.createElement(window.SystemsStatus, {
    items: D.situacaoAtual
  }), /*#__PURE__*/React.createElement(window.AlarmsSection, {
    rows: D.alarmes
  }), /*#__PURE__*/React.createElement(window.AnomaliesSection, {
    rows: D.anomalias
  }), /*#__PURE__*/React.createElement(window.NextSteps, {
    steps: D.proximosPassos
  }), /*#__PURE__*/React.createElement(window.DetailSection, {
    data: D
  }), /*#__PURE__*/React.createElement(window.AnnexDivider, {
    total: D.resumo.length,
    expanded: annexOpen,
    onToggle: () => setAnnexOpen(a => !a)
  }), annexOpen && /*#__PURE__*/React.createElement(window.ResumoTable, {
    rows: D.resumo
  }), /*#__PURE__*/React.createElement(window.ExecFooter, {
    cover: D.cover
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 8
    }
  }))), /*#__PURE__*/React.createElement(Toasts, {
    toasts: toasts
  }));
}
Object.assign(window, {
  Report
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/relatorios/Report.jsx", error: String((e && e.message) || e) }); }

// ui_kits/relatorios/ReportMid.jsx
try { (() => {
/* Relatórios — Alarmes (05), Anomalias (06), Próximos Passos (07) */
const RM = window.AegisDesignSystem_86ea41;

/* Shared: criticidade legend */
function CritLegend() {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 16,
      flexWrap: 'wrap'
    }
  }, [['Baixa', 'var(--good-foreground)'], ['Média', 'var(--alert-foreground)'], ['Alta', 'var(--bad-foreground)']].map(([l, c]) => /*#__PURE__*/React.createElement("span", {
    key: l,
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 7,
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)',
      fontWeight: 500
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 11,
      height: 11,
      borderRadius: 3,
      background: c
    }
  }), " ", l, " criticidade")));
}

/* Shared: code + ranking table with proportional event bars */
function EventTable({
  rows,
  codeLabel,
  codeMono
}) {
  const M = window.REL_MAPS;
  const max = Math.max(...rows.map(r => r.eventos));
  const ranked = [...rows].sort((a, b) => b.eventos - a.eventos);
  const cols = [codeLabel, 'Criticidade', 'Descrição', 'Sistemas', 'Eventos'];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '1.55fr 1fr',
      gap: 18
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-lg)',
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      overflowX: 'auto'
    }
  }, /*#__PURE__*/React.createElement("table", {
    style: {
      width: '100%',
      borderCollapse: 'collapse',
      minWidth: 460
    }
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", {
    style: {
      background: 'var(--surface-muted)'
    }
  }, cols.map((c, i) => /*#__PURE__*/React.createElement("th", {
    key: i,
    style: {
      textAlign: i === 4 ? 'right' : 'left',
      padding: '11px 14px',
      fontSize: 'var(--text-2xs)',
      fontWeight: 700,
      letterSpacing: '0.06em',
      textTransform: 'uppercase',
      color: 'var(--text-muted)',
      whiteSpace: 'nowrap'
    }
  }, c)))), /*#__PURE__*/React.createElement("tbody", null, rows.map(r => /*#__PURE__*/React.createElement("tr", {
    key: r.codigo,
    className: "rel-row",
    style: {
      borderTop: '1px solid var(--border-subtle)'
    }
  }, /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '12px 14px',
      whiteSpace: 'nowrap'
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: codeMono ? 'aegis-mono' : '',
    style: {
      fontSize: 'var(--text-sm)',
      fontWeight: 700,
      color: 'var(--text-strong)'
    }
  }, r.codigo)), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '12px 14px'
    }
  }, /*#__PURE__*/React.createElement(RM.Badge, {
    tone: M.CRIT_TONE[r.criticidade],
    dot: true,
    size: "sm"
  }, r.criticidade)), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '12px 14px',
      minWidth: 180
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-body)'
    }
  }, r.descricao)), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '12px 14px'
    }
  }, r.sistemas.map((s, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)',
      lineHeight: 1.4
    }
  }, s))), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '12px 14px',
      textAlign: 'right'
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "aegis-tnum",
    style: {
      fontSize: 'var(--text-sm)',
      fontWeight: 700,
      color: 'var(--text-strong)'
    }
  }, r.eventos)))))))), /*#__PURE__*/React.createElement("div", {
    style: {
      border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-lg)',
      padding: '16px 18px',
      background: 'var(--surface-muted)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-2xs)',
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.06em',
      color: 'var(--text-faint)',
      marginBottom: 14
    }
  }, "Ranking por quantidade de eventos"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 14
    }
  }, ranked.map(r => {
    const c = M.CRIT_DOT[r.criticidade];
    return /*#__PURE__*/React.createElement("div", {
      key: r.codigo
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 8,
        marginBottom: 5
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: codeMono ? 'aegis-mono' : '',
      style: {
        fontSize: 'var(--text-xs)',
        fontWeight: 700,
        color: 'var(--text-strong)'
      }
    }, r.codigo), /*#__PURE__*/React.createElement("span", {
      className: "aegis-tnum",
      style: {
        fontSize: 'var(--text-xs)',
        fontWeight: 700,
        color: 'var(--text-body)'
      }
    }, r.eventos)), /*#__PURE__*/React.createElement("div", {
      style: {
        height: 9,
        borderRadius: 'var(--radius-pill)',
        background: 'var(--border-subtle)',
        overflow: 'hidden'
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        height: '100%',
        width: `${Math.max(6, r.eventos / max * 100)}%`,
        background: c,
        borderRadius: 'var(--radius-pill)'
      }
    })));
  }))));
}
function AlarmsSection({
  rows
}) {
  return /*#__PURE__*/React.createElement(PanelCard, {
    id: "sec-alarmes"
  }, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "bell-ring",
    iconTone: "amber",
    eyebrow: "05 \xB7 Per\xEDodo",
    title: "Principais Alarmes do Per\xEDodo",
    right: /*#__PURE__*/React.createElement(CritLegend, null)
  }), /*#__PURE__*/React.createElement(EventTable, {
    rows: rows,
    codeLabel: "C\xF3digo do Alarme",
    codeMono: true
  }));
}
function AnomaliesSection({
  rows
}) {
  return /*#__PURE__*/React.createElement(PanelCard, {
    id: "sec-anomalias"
  }, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "activity",
    iconTone: "violet",
    eyebrow: "06 \xB7 Per\xEDodo",
    title: "Principais Anomalias do Per\xEDodo",
    right: /*#__PURE__*/React.createElement(CritLegend, null)
  }), /*#__PURE__*/React.createElement(EventTable, {
    rows: rows,
    codeLabel: "C\xF3digo da Anomalia",
    codeMono: false
  }));
}

/* ===================== 07 — Próximos Passos (accordion) ===================== */
const ACTION_STATUS_TONE = {
  'Pendente': 'alert',
  'Em andamento': 'brand',
  'Concluído': 'good'
};
function NextStepRow({
  step,
  open,
  onToggle
}) {
  const M = window.REL_MAPS;
  const condTone = M.STATUS_TONE[step.condicao] || 'neutral';
  const condColor = condTone === 'bad' ? 'var(--bad-foreground)' : condTone === 'alert' ? 'var(--alert-foreground)' : 'var(--brand)';
  return /*#__PURE__*/React.createElement("div", {
    style: {
      border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-lg)',
      overflow: 'hidden',
      background: 'var(--surface-card)',
      borderLeft: `3px solid ${condColor}`
    }
  }, /*#__PURE__*/React.createElement("button", {
    onClick: onToggle,
    className: "rel-acc-head",
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 14,
      width: '100%',
      padding: '14px 16px',
      border: 'none',
      background: 'transparent',
      cursor: 'pointer',
      textAlign: 'left'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 36,
      height: 36,
      flex: 'none',
      borderRadius: 'var(--radius-md)',
      background: 'var(--surface-muted)',
      color: condColor
    }
  }, /*#__PURE__*/React.createElement(RM.Icon, {
    name: "wrench",
    size: 17
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 9,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-sm)',
      fontWeight: 700,
      color: 'var(--text-strong)'
    }
  }, step.sistema), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)'
    }
  }, "\xB7 ", step.local)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      flexWrap: 'wrap',
      marginTop: 6
    }
  }, /*#__PURE__*/React.createElement(RM.Badge, {
    tone: condTone,
    dot: true,
    size: "sm"
  }, step.condicao), /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 5,
      fontSize: 'var(--text-2xs)',
      color: 'var(--text-faint)'
    }
  }, /*#__PURE__*/React.createElement(RM.Icon, {
    name: "flag",
    size: 12
  }), "Prioridade ", step.prioridade))), /*#__PURE__*/React.createElement(RM.Badge, {
    tone: ACTION_STATUS_TONE[step.statusAcao],
    size: "sm"
  }, step.statusAcao), /*#__PURE__*/React.createElement(RM.Icon, {
    name: open ? 'chevron-up' : 'chevron-down',
    size: 18,
    color: "var(--text-faint)"
  })), open && /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '4px 16px 18px 66px',
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: 20
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-2xs)',
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.05em',
      color: 'var(--bad-foreground)',
      marginBottom: 8
    }
  }, "Riscos atuais"), step.riscos.map((r, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: 'flex',
      gap: 8,
      fontSize: 'var(--text-sm)',
      color: 'var(--text-body)',
      lineHeight: 1.5,
      marginBottom: 5
    }
  }, /*#__PURE__*/React.createElement(RM.Icon, {
    name: "alert-triangle",
    size: 14,
    color: "var(--bad-foreground)",
    style: {
      flex: 'none',
      marginTop: 3
    }
  }), r))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-2xs)',
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.05em',
      color: 'var(--brand-strong)',
      marginBottom: 8
    }
  }, "O que fazer"), step.acoes.map((a, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: 'flex',
      gap: 8,
      fontSize: 'var(--text-sm)',
      color: 'var(--text-body)',
      lineHeight: 1.5,
      marginBottom: 5
    }
  }, /*#__PURE__*/React.createElement(RM.Icon, {
    name: "check",
    size: 14,
    color: "var(--brand)",
    style: {
      flex: 'none',
      marginTop: 3
    }
  }), a))), /*#__PURE__*/React.createElement("div", {
    style: {
      gridColumn: '1 / -1',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 14,
      flexWrap: 'wrap',
      paddingTop: 14,
      borderTop: '1px solid var(--border-subtle)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 20,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 7,
      fontSize: 'var(--text-xs)',
      color: 'var(--text-body)'
    }
  }, /*#__PURE__*/React.createElement(RM.Icon, {
    name: "user",
    size: 14,
    color: "var(--text-faint)"
  }), "Respons\xE1vel: ", /*#__PURE__*/React.createElement("b", {
    style: {
      color: 'var(--text-strong)'
    }
  }, step.responsavel)), /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 7,
      fontSize: 'var(--text-xs)',
      color: 'var(--text-body)'
    }
  }, /*#__PURE__*/React.createElement(RM.Icon, {
    name: "calendar-clock",
    size: 14,
    color: "var(--text-faint)"
  }), "Prazo: ", /*#__PURE__*/React.createElement("b", {
    style: {
      color: 'var(--text-strong)'
    }
  }, step.prazo))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 8,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement(RM.Button, {
    variant: "secondary",
    size: "sm",
    icon: "plus"
  }, "Criar tarefa"), /*#__PURE__*/React.createElement(RM.Button, {
    variant: "secondary",
    size: "sm",
    icon: "play"
  }, "Em andamento"), /*#__PURE__*/React.createElement(RM.Button, {
    variant: "primary",
    size: "sm",
    icon: "check-check"
  }, "Concluir")))));
}
function NextSteps({
  steps
}) {
  const [open, setOpen] = React.useState({
    0: true
  });
  return /*#__PURE__*/React.createElement(PanelCard, {
    id: "sec-passos"
  }, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "list-checks",
    iconTone: "brand",
    eyebrow: "07 \xB7 Plano de a\xE7\xE3o",
    title: "Pr\xF3ximos Passos",
    subtitle: "Roteiro priorizado de a\xE7\xF5es corretivas e preditivas por sistema.",
    right: /*#__PURE__*/React.createElement(RM.Badge, {
      tone: "brand",
      dot: true
    }, steps.length, " a\xE7\xF5es")
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 10
    }
  }, steps.map((s, i) => /*#__PURE__*/React.createElement(NextStepRow, {
    key: i,
    step: s,
    open: !!open[i],
    onToggle: () => setOpen(o => ({
      ...o,
      [i]: !o[i]
    }))
  }))));
}
Object.assign(window, {
  AlarmsSection,
  AnomaliesSection,
  NextSteps
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/relatorios/ReportMid.jsx", error: String((e && e.message) || e) }); }

// ui_kits/relatorios/ReportTech.jsx
try { (() => {
/* Relatórios — Detalhamento técnico (08–10), Anexo (11), Resumo (12), Rodapé (13) */
const RX = window.AegisDesignSystem_86ea41;

/* ===================== 08–10 — Matriz técnica ===================== */
function MatrixCell({
  value,
  cols
}) {
  const M = window.REL_MAPS;
  const [bg, fg] = M.CELL_COLOR[value] || ['var(--surface-muted)', 'var(--text-muted)'];
  const ic = value === 'Normal' ? 'check' : value === 'Atenção' ? 'minus' : 'alert-triangle';
  return /*#__PURE__*/React.createElement("td", {
    title: value,
    style: {
      padding: 6,
      textAlign: 'center',
      borderLeft: '1px solid var(--border-subtle)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 28,
      height: 28,
      borderRadius: 'var(--radius-sm)',
      background: bg,
      color: fg
    }
  }, /*#__PURE__*/React.createElement(RX.Icon, {
    name: ic,
    size: 14
  })));
}
function TechMatrix({
  rows,
  cols
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-lg)',
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      overflowX: 'auto'
    }
  }, /*#__PURE__*/React.createElement("table", {
    style: {
      width: '100%',
      borderCollapse: 'collapse',
      minWidth: 760
    }
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", {
    style: {
      background: 'var(--surface-muted)'
    }
  }, /*#__PURE__*/React.createElement("th", {
    style: {
      textAlign: 'left',
      padding: '11px 14px',
      position: 'sticky',
      left: 0,
      background: 'var(--surface-muted)',
      fontSize: 'var(--text-2xs)',
      fontWeight: 700,
      letterSpacing: '0.05em',
      textTransform: 'uppercase',
      color: 'var(--text-muted)',
      whiteSpace: 'nowrap',
      zIndex: 1
    }
  }, "Sistema"), cols.map(c => /*#__PURE__*/React.createElement("th", {
    key: c,
    style: {
      padding: '11px 8px',
      borderLeft: '1px solid var(--border-subtle)',
      fontSize: 9,
      fontWeight: 700,
      letterSpacing: '0.03em',
      textTransform: 'uppercase',
      color: 'var(--text-muted)',
      verticalAlign: 'bottom',
      minWidth: 78
    }
  }, c)))), /*#__PURE__*/React.createElement("tbody", null, rows.map(r => /*#__PURE__*/React.createElement("tr", {
    key: r.sistema,
    className: "rel-row",
    style: {
      borderTop: '1px solid var(--border-subtle)'
    }
  }, /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '8px 14px',
      position: 'sticky',
      left: 0,
      background: 'var(--surface-card)',
      fontSize: 'var(--text-xs)',
      fontWeight: 700,
      color: 'var(--text-strong)',
      whiteSpace: 'nowrap',
      zIndex: 1
    }
  }, r.sistema), r.cells.map((v, i) => /*#__PURE__*/React.createElement(MatrixCell, {
    key: i,
    value: v
  }))))))));
}
function TechComments({
  comments
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 16,
      display: 'flex',
      flexDirection: 'column',
      gap: 9
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-2xs)',
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.06em',
      color: 'var(--text-faint)'
    }
  }, "Coment\xE1rios t\xE9cnicos"), comments.map((c, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: 'flex',
      gap: 10,
      padding: '11px 14px',
      borderRadius: 'var(--radius-md)',
      background: 'var(--surface-muted)',
      border: '1px solid var(--border-subtle)'
    }
  }, /*#__PURE__*/React.createElement(RX.Icon, {
    name: "message-square-text",
    size: 15,
    color: "var(--text-faint)",
    style: {
      flex: 'none',
      marginTop: 2
    }
  }), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-body)',
      lineHeight: 1.5
    }
  }, c))));
}
function DetailSection({
  data
}) {
  const [tab, setTab] = React.useState('risco');
  const isRisk = tab === 'risco';
  const rows = isRisk ? data.matrizRisco : data.matrizAtencao;
  const comments = isRisk ? data.comentariosRisco : data.comentariosAtencao;
  return /*#__PURE__*/React.createElement(PanelCard, {
    id: "sec-detalhamento"
  }, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "microscope",
    iconTone: "violet",
    eyebrow: "08 \xB7 An\xE1lise t\xE9cnica",
    title: "Detalhamento das Anomalias e Alarmes",
    subtitle: "An\xE1lise detalhada do desempenho e condi\xE7\xF5es dos sistemas, agrupada por n\xEDvel de risco.",
    right: /*#__PURE__*/React.createElement(StatusLegend, null)
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 6,
      padding: 4,
      background: 'var(--surface-muted)',
      borderRadius: 'var(--radius-pill)',
      width: 'fit-content',
      marginBottom: 18
    }
  }, [['risco', '09 · Risco de Quebra', data.matrizRisco.length], ['atencao', '10 · Em Atenção', data.matrizAtencao.length]].map(([id, label, n]) => /*#__PURE__*/React.createElement("button", {
    key: id,
    onClick: () => setTab(id),
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 8,
      padding: '8px 16px',
      border: 'none',
      cursor: 'pointer',
      borderRadius: 'var(--radius-pill)',
      fontFamily: 'var(--font-sans)',
      fontSize: 'var(--text-sm)',
      fontWeight: 600,
      background: tab === id ? 'var(--surface-card)' : 'transparent',
      color: tab === id ? 'var(--text-strong)' : 'var(--text-muted)',
      boxShadow: tab === id ? 'var(--shadow-sm)' : 'none'
    }
  }, label, /*#__PURE__*/React.createElement("span", {
    className: "aegis-tnum",
    style: {
      fontSize: 'var(--text-2xs)',
      fontWeight: 700,
      padding: '1px 7px',
      borderRadius: 'var(--radius-pill)',
      background: tab === id ? 'var(--brand-soft)' : 'var(--border-subtle)',
      color: tab === id ? 'var(--brand-strong)' : 'var(--text-muted)'
    }
  }, n)))), /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: 4,
      fontSize: 'var(--text-base)',
      fontWeight: 700,
      color: 'var(--text-strong)'
    }
  }, isRisk ? 'Condição Geral dos Sistemas com Risco de Quebra' : 'Condição Geral dos Sistemas em Atenção'), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)',
      marginBottom: 16
    }
  }, "Matriz t\xE9cnica por sistema \xB7 status por par\xE2metro de opera\xE7\xE3o"), /*#__PURE__*/React.createElement(TechMatrix, {
    rows: rows,
    cols: data.matrizCols
  }), /*#__PURE__*/React.createElement(TechComments, {
    comments: comments
  }));
}

/* ===================== 11 — Anexo I (divider) ===================== */
function AnnexDivider({
  total,
  expanded,
  onToggle
}) {
  return /*#__PURE__*/React.createElement(PanelCard, {
    id: "sec-anexo",
    style: {
      background: 'var(--surface-muted)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 18,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 14,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 44,
      height: 44,
      flex: 'none',
      borderRadius: 'var(--radius-lg)',
      background: 'var(--brand-soft)',
      color: 'var(--brand-strong)'
    }
  }, /*#__PURE__*/React.createElement(RX.Icon, {
    name: "paperclip",
    size: 21
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10
    }
  }, /*#__PURE__*/React.createElement(SectionTag, {
    n: "11"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-2xs)',
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
      color: 'var(--text-faint)'
    }
  }, "Anexo")), /*#__PURE__*/React.createElement("h3", {
    style: {
      fontSize: 'var(--text-xl)',
      fontWeight: 800,
      color: 'var(--text-strong)',
      marginTop: 4
    }
  }, "Anexo I \u2014 Rela\xE7\xE3o de Equipamentos e Sistemas"), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-muted)',
      marginTop: 3
    }
  }, "Lista completa dos sistemas monitorados no site, separada do conte\xFAdo t\xE9cnico principal."))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      textAlign: 'right'
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "aegis-tnum",
    style: {
      fontSize: 26,
      fontWeight: 800,
      color: 'var(--text-strong)',
      lineHeight: 1
    }
  }, total), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-2xs)',
      color: 'var(--text-faint)',
      fontWeight: 600,
      textTransform: 'uppercase',
      letterSpacing: '0.05em'
    }
  }, "Sistemas")), /*#__PURE__*/React.createElement(RX.Button, {
    variant: "secondary",
    size: "sm",
    icon: "download"
  }, "Exportar lista"), /*#__PURE__*/React.createElement(RX.Button, {
    variant: expanded ? 'ghost' : 'primary',
    size: "sm",
    icon: expanded ? 'chevron-up' : 'chevron-down',
    onClick: onToggle
  }, expanded ? 'Ocultar anexo' : 'Expandir anexo'))));
}

/* ===================== 12 — Resumo dos Sistemas ===================== */
function ResumoTable({
  rows
}) {
  const M = window.REL_MAPS;
  const [q, setQ] = React.useState('');
  const [status, setStatus] = React.useState('todos');
  const [fab, setFab] = React.useState('todos');
  const [page, setPage] = React.useState(1);
  const perPage = 8;
  const filtered = rows.filter(r => {
    const matchQ = !q || r.nome.toLowerCase().includes(q.toLowerCase()) || r.local.toLowerCase().includes(q.toLowerCase());
    const matchS = status === 'todos' || r.status === status;
    const matchF = fab === 'todos' || r.fab.toLowerCase() === fab;
    return matchQ && matchS && matchF;
  });
  const pages = Math.max(1, Math.ceil(filtered.length / perPage));
  const cur = Math.min(page, pages);
  const view = filtered.slice((cur - 1) * perPage, cur * perPage);
  const cols = ['Nome do Sistema', 'Local Atendido', 'Fabricante', 'Capacidade', 'Evaporadoras', 'Modelos', 'Status do Mês'];
  React.useEffect(() => {
    setPage(1);
  }, [q, status, fab]);
  return /*#__PURE__*/React.createElement(PanelCard, {
    id: "sec-resumo",
    style: {
      padding: 0,
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 'var(--space-5)',
      paddingBottom: 16
    }
  }, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "server",
    iconTone: "brand",
    eyebrow: "12 \xB7 Invent\xE1rio",
    title: "Resumo dos Sistemas",
    right: /*#__PURE__*/React.createElement(RX.Badge, {
      tone: "brand"
    }, rows.length, " sistemas")
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement(RX.Input, {
    icon: /*#__PURE__*/React.createElement(RX.Icon, {
      name: "search",
      size: 15
    }),
    placeholder: "Buscar por sistema ou local\u2026",
    value: q,
    onChange: e => setQ(e.target.value),
    wrapStyle: {
      width: 280
    }
  }), /*#__PURE__*/React.createElement(RX.Select, {
    options: [{
      label: 'Todos os status',
      value: 'todos'
    }, {
      label: 'Normal',
      value: 'Normal'
    }, {
      label: 'Atenção',
      value: 'Atenção'
    }, {
      label: 'Ação Imediata',
      value: 'Ação Imediata'
    }],
    value: status,
    onChange: setStatus,
    shape: "pill",
    size: "sm",
    fullWidth: false,
    wrapStyle: {
      width: 180
    }
  }), /*#__PURE__*/React.createElement(RX.Select, {
    options: [{
      label: 'Todos os fabricantes',
      value: 'todos'
    }, {
      label: 'LG',
      value: 'lg'
    }],
    value: fab,
    onChange: setFab,
    shape: "pill",
    size: "sm",
    fullWidth: false,
    wrapStyle: {
      width: 190
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement(RX.Button, {
    variant: "secondary",
    size: "sm",
    icon: "download"
  }, "Exportar CSV/XLS"))), /*#__PURE__*/React.createElement("div", {
    style: {
      overflowX: 'auto'
    }
  }, /*#__PURE__*/React.createElement("table", {
    style: {
      width: '100%',
      borderCollapse: 'collapse',
      minWidth: 880
    }
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", {
    style: {
      background: 'var(--surface-muted)'
    }
  }, cols.map((c, i) => /*#__PURE__*/React.createElement("th", {
    key: i,
    style: {
      textAlign: i >= 3 && i <= 4 ? 'center' : 'left',
      padding: '11px 16px',
      fontSize: 'var(--text-2xs)',
      fontWeight: 700,
      letterSpacing: '0.06em',
      textTransform: 'uppercase',
      color: 'var(--text-muted)',
      whiteSpace: 'nowrap'
    }
  }, c)))), /*#__PURE__*/React.createElement("tbody", null, view.map(r => /*#__PURE__*/React.createElement("tr", {
    key: r.nome,
    className: "rel-row",
    style: {
      borderTop: '1px solid var(--border-subtle)'
    }
  }, /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '12px 16px',
      whiteSpace: 'nowrap'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-sm)',
      fontWeight: 700,
      color: 'var(--text-strong)'
    }
  }, r.nome)), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '12px 16px',
      whiteSpace: 'nowrap'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-body)'
    }
  }, r.local)), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '12px 16px'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-body)'
    }
  }, r.fab)), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '12px 16px',
      textAlign: 'center'
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "aegis-mono",
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-body)'
    }
  }, r.cap)), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '12px 16px',
      textAlign: 'center'
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "aegis-tnum",
    style: {
      fontSize: 'var(--text-sm)',
      fontWeight: 600,
      color: 'var(--text-strong)'
    }
  }, r.evap)), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '12px 16px'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-body)'
    }
  }, r.modelo)), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '12px 16px'
    }
  }, /*#__PURE__*/React.createElement(RX.Badge, {
    tone: M.STATUS_TONE[r.status],
    dot: true,
    size: "sm"
  }, r.status)))), view.length === 0 && /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("td", {
    colSpan: cols.length,
    style: {
      padding: '40px 16px',
      textAlign: 'center'
    }
  }, /*#__PURE__*/React.createElement(RX.Icon, {
    name: "search-x",
    size: 28,
    color: "var(--text-faint)"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-muted)',
      marginTop: 10
    }
  }, "Nenhum sistema encontrado para os filtros selecionados.")))))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 16,
      padding: '14px 22px',
      borderTop: '1px solid var(--border-subtle)',
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)'
    }
  }, "Mostrando ", /*#__PURE__*/React.createElement("b", {
    style: {
      color: 'var(--text-strong)'
    }
  }, view.length === 0 ? 0 : (cur - 1) * perPage + 1, "\u2013", (cur - 1) * perPage + view.length), " de ", filtered.length, " sistemas"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 6
    }
  }, /*#__PURE__*/React.createElement(RX.IconButton, {
    icon: "chevron-left",
    label: "Anterior",
    variant: "soft",
    size: "sm",
    onClick: () => setPage(p => Math.max(1, p - 1))
  }), Array.from({
    length: pages
  }, (_, i) => i + 1).map(p => /*#__PURE__*/React.createElement("button", {
    key: p,
    onClick: () => setPage(p),
    style: {
      width: 32,
      height: 32,
      borderRadius: 'var(--radius-md)',
      border: p === cur ? '1px solid transparent' : '1px solid var(--control-border)',
      background: p === cur ? 'var(--brand)' : 'var(--control-bg)',
      color: p === cur ? '#fff' : 'var(--text-body)',
      fontSize: 'var(--text-sm)',
      fontWeight: 600,
      cursor: 'pointer',
      fontFamily: 'var(--font-sans)'
    }
  }, p)), /*#__PURE__*/React.createElement(RX.IconButton, {
    icon: "chevron-right",
    label: "Pr\xF3ximo",
    variant: "soft",
    size: "sm",
    onClick: () => setPage(p => Math.min(pages, p + 1))
  }))));
}

/* ===================== 13 — Rodapé Executivo ===================== */
function ExecFooter({
  cover
}) {
  const col = (title, icon, rows) => /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 9
    }
  }, /*#__PURE__*/React.createElement(RX.Icon, {
    name: icon,
    size: 16,
    color: "var(--brand)"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-2xs)',
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
      color: 'var(--text-faint)'
    }
  }, title)), rows.map(([k, v]) => /*#__PURE__*/React.createElement("div", {
    key: k,
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)'
    }
  }, k), /*#__PURE__*/React.createElement("span", {
    className: k === 'Código' ? 'aegis-mono' : '',
    style: {
      fontSize: 'var(--text-xs)',
      fontWeight: 600,
      color: 'var(--text-strong)',
      textAlign: 'right'
    }
  }, v))));
  return /*#__PURE__*/React.createElement(PanelCard, {
    id: "sec-rodape",
    style: {
      background: 'var(--surface-header)',
      border: 'none'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(3, 1fr)',
      gap: 28
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 9
    }
  }, /*#__PURE__*/React.createElement(RX.Icon, {
    name: "file-text",
    size: 16,
    color: "var(--categorical-2)"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-2xs)',
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
      color: 'rgba(231,237,245,0.5)'
    }
  }, "Documento")), [['Código', cover.codigo], ['Versão', cover.versao], ['Emissão', cover.dataEmissao], ['Período', cover.periodo]].map(([k, v]) => /*#__PURE__*/React.createElement("div", {
    key: k,
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'rgba(231,237,245,0.55)'
    }
  }, k), /*#__PURE__*/React.createElement("span", {
    className: "aegis-mono",
    style: {
      fontSize: 'var(--text-xs)',
      fontWeight: 600,
      color: '#F5F7FA',
      textAlign: 'right'
    }
  }, v)))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 9
    }
  }, /*#__PURE__*/React.createElement(RX.Icon, {
    name: "user-check",
    size: 16,
    color: "var(--categorical-2)"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-2xs)',
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
      color: 'rgba(231,237,245,0.5)'
    }
  }, "Respons\xE1vel t\xE9cnico")), [['Cliente', cover.cliente], ['Site', cover.site], ['Gestor', 'Jairo Souza'], ['Especialista', cover.responsavel]].map(([k, v]) => /*#__PURE__*/React.createElement("div", {
    key: k,
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'rgba(231,237,245,0.55)'
    }
  }, k), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-xs)',
      fontWeight: 600,
      color: '#F5F7FA',
      textAlign: 'right'
    }
  }, v))), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 6,
      padding: '10px 14px',
      borderRadius: 'var(--radius-md)',
      background: 'rgba(255,255,255,0.05)',
      border: '1px solid rgba(255,255,255,0.08)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 9,
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
      color: 'rgba(231,237,245,0.5)',
      marginBottom: 4
    }
  }, "Assinatura digital"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(RX.Icon, {
    name: "shield-check",
    size: 16,
    color: "#36E07A"
  }), /*#__PURE__*/React.createElement("span", {
    className: "aegis-mono",
    style: {
      fontSize: 'var(--text-xs)',
      color: '#9BF0B5'
    }
  }, "Verificada \xB7 ", cover.responsavel)))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 14,
      justifyContent: 'space-between'
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 11,
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: window.__resources && window.__resources.aegisLogo || '../../assets/aegis-symbol-white.png',
    alt: "Aegis",
    style: {
      height: 30
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 21,
      fontWeight: 800,
      letterSpacing: '-0.5px',
      color: '#F5F7FA'
    }
  }, "Aegis")), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'rgba(231,237,245,0.6)',
      lineHeight: 1.55
    }
  }, "Plataforma de monitoramento operacional e an\xE1lise de sa\xFAde dos sistemas. Relat\xF3rio gerado automaticamente a partir dos dados monitorados no per\xEDodo.")), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-2xs)',
      color: 'rgba(231,237,245,0.4)'
    }
  }, "\xA9 2026 Aegis \xB7 Todos os direitos reservados"))));
}
Object.assign(window, {
  DetailSection,
  AnnexDivider,
  ResumoTable,
  ExecFooter
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/relatorios/ReportTech.jsx", error: String((e && e.message) || e) }); }

// ui_kits/relatorios/ReportTop.jsx
try { (() => {
/* Relatórios — Cover (01), Team (02), Condition (03), Systems Status (04) */
const RT = window.AegisDesignSystem_86ea41;

/* ===================== 01 — Capa / Identificação ===================== */
function ReportCover({
  cover
}) {
  const meta = [['Cliente', cover.cliente, 'building-2'], ['Site', cover.site, 'map-pin'], ['Mês de referência', cover.mesReferencia, 'calendar'], ['Período de análise', cover.periodo, 'calendar-range'], ['Código do relatório', cover.codigo, 'hash'], ['Versão', cover.versao, 'git-commit-horizontal'], ['Data de emissão', cover.dataEmissao, 'calendar-check'], ['Responsável técnico', cover.responsavel, 'user-check']];
  return /*#__PURE__*/React.createElement(PanelCard, {
    id: "sec-capa",
    style: {
      padding: 0,
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative',
      background: 'var(--surface-header)',
      padding: '30px 32px 28px',
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      inset: 0,
      background: 'radial-gradient(900px 300px at 88% -40%, rgba(255,140,0,0.22), transparent 70%)',
      pointerEvents: 'none'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative',
      display: 'flex',
      alignItems: 'flex-start',
      justifyContent: 'space-between',
      gap: 24,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0,
      maxWidth: 640
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement(SectionTag, {
    n: "01"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-2xs)',
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.12em',
      color: 'rgba(231,237,245,0.6)'
    }
  }, "Capa \xB7 Identifica\xE7\xE3o do relat\xF3rio")), /*#__PURE__*/React.createElement("h2", {
    style: {
      fontSize: 32,
      fontWeight: 800,
      letterSpacing: '-0.6px',
      color: '#F5F7FA',
      lineHeight: 1.08
    }
  }, cover.titulo), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 'var(--text-base)',
      color: 'rgba(231,237,245,0.72)',
      marginTop: 10,
      lineHeight: 1.5
    }
  }, cover.subtitulo)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'flex-end',
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 7,
      padding: '6px 13px',
      borderRadius: 'var(--radius-pill)',
      background: 'rgba(3,150,2,0.18)',
      border: '1px solid rgba(3,252,3,0.22)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 7,
      height: 7,
      borderRadius: '50%',
      background: '#36E07A'
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-xs)',
      fontWeight: 700,
      color: '#9BF0B5'
    }
  }, cover.status)), /*#__PURE__*/React.createElement("div", {
    className: "aegis-mono",
    style: {
      fontSize: 'var(--text-xs)',
      color: 'rgba(231,237,245,0.55)',
      textAlign: 'right'
    }
  }, cover.codigo, /*#__PURE__*/React.createElement("br", null), cover.versao, " \xB7 emitido ", cover.dataEmissao)))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(4, 1fr)',
      gap: 1,
      background: 'var(--border-subtle)',
      borderTop: '1px solid var(--border-subtle)'
    }
  }, meta.map(([label, value, icon]) => /*#__PURE__*/React.createElement("div", {
    key: label,
    style: {
      background: 'var(--surface-card)',
      padding: '16px 18px',
      display: 'flex',
      alignItems: 'flex-start',
      gap: 11,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 30,
      height: 30,
      flex: 'none',
      borderRadius: 'var(--radius-md)',
      background: 'var(--surface-muted)',
      color: 'var(--text-muted)'
    }
  }, /*#__PURE__*/React.createElement(RT.Icon, {
    name: icon,
    size: 15
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-2xs)',
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.05em',
      color: 'var(--text-faint)',
      marginBottom: 3
    }
  }, label), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-sm)',
      fontWeight: 600,
      color: 'var(--text-strong)',
      lineHeight: 1.3
    }
  }, value))))));
}

/* ===================== 02 — Time Envolvido ===================== */
function TeamSection({
  team
}) {
  return /*#__PURE__*/React.createElement(PanelCard, {
    id: "sec-time"
  }, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "users",
    iconTone: "brand",
    eyebrow: "02 \xB7 Equipe",
    title: "Time Envolvido",
    subtitle: "Respons\xE1veis t\xE9cnicos e gerenciais pelo acompanhamento dos sistemas no per\xEDodo."
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(2, 1fr)',
      gap: 16
    }
  }, team.map(m => /*#__PURE__*/React.createElement("div", {
    key: m.funcao,
    style: {
      display: 'flex',
      gap: 14,
      padding: 18,
      borderRadius: 'var(--radius-lg)',
      border: '1px solid var(--border-subtle)',
      background: 'var(--surface-muted)'
    }
  }, /*#__PURE__*/React.createElement(RT.Avatar, {
    name: m.nome,
    size: "lg"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0,
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      flexWrap: 'wrap',
      marginBottom: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-2xs)',
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.06em',
      color: 'var(--brand-strong)'
    }
  }, m.funcao), /*#__PURE__*/React.createElement(RT.Badge, {
    tone: "brand",
    size: "sm"
  }, m.badge)), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-lg)',
      fontWeight: 700,
      color: 'var(--text-strong)'
    }
  }, m.nome), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)',
      marginTop: 1
    }
  }, m.empresa), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 16,
      flexWrap: 'wrap',
      marginTop: 11
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      fontSize: 'var(--text-xs)',
      color: 'var(--text-body)'
    }
  }, /*#__PURE__*/React.createElement(RT.Icon, {
    name: "mail",
    size: 14,
    color: "var(--text-faint)"
  }), m.email), /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      fontSize: 'var(--text-xs)',
      color: 'var(--text-body)'
    }
  }, /*#__PURE__*/React.createElement(RT.Icon, {
    name: "phone",
    size: 14,
    color: "var(--text-faint)"
  }), m.telefone)))))));
}

/* ===================== 03 — Condição Geral ===================== */
function ConditionSection({
  items
}) {
  const M = window.REL_MAPS;
  return /*#__PURE__*/React.createElement(PanelCard, {
    id: "sec-condicao"
  }, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "clipboard-list",
    iconTone: "amber",
    eyebrow: "03 \xB7 Resumo executivo",
    title: "Como est\xE1 a condi\xE7\xE3o geral da climatiza\xE7\xE3o?",
    subtitle: "Principais pontos de aten\xE7\xE3o identificados no per\xEDodo de an\xE1lise.",
    right: /*#__PURE__*/React.createElement(StatusLegend, {
      items: [['Atenção', 'var(--alert-foreground)'], ['Ação Imediata', 'var(--bad-foreground)'], ['Crítico', 'var(--bad-foreground)']]
    })
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fill, minmax(330px, 1fr))',
      gap: 14
    }
  }, items.map((it, i) => {
    const tone = M.STATUS_TONE[it.severidade] || 'neutral';
    const accent = tone === 'bad' ? 'var(--bad-foreground)' : tone === 'alert' ? 'var(--alert-foreground)' : 'var(--brand)';
    const soft = tone === 'bad' ? 'var(--bad-background)' : tone === 'alert' ? 'var(--alert-background)' : 'var(--brand-soft)';
    return /*#__PURE__*/React.createElement("div", {
      key: i,
      className: "rel-hovercard",
      style: {
        position: 'relative',
        display: 'flex',
        gap: 13,
        padding: '16px 18px 16px 20px',
        borderRadius: 'var(--radius-lg)',
        border: '1px solid var(--border-subtle)',
        background: 'var(--surface-card)',
        borderLeft: `3px solid ${accent}`
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 36,
        height: 36,
        flex: 'none',
        borderRadius: 'var(--radius-md)',
        background: soft,
        color: accent
      }
    }, /*#__PURE__*/React.createElement(RT.Icon, {
      name: it.icon,
      size: 18
    })), /*#__PURE__*/React.createElement("div", {
      style: {
        minWidth: 0
      }
    }, /*#__PURE__*/React.createElement("p", {
      style: {
        fontSize: 'var(--text-sm)',
        fontWeight: 600,
        color: 'var(--text-strong)',
        lineHeight: 1.4
      }
    }, it.texto), /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        flexWrap: 'wrap',
        marginTop: 10
      }
    }, /*#__PURE__*/React.createElement(RT.Badge, {
      tone: tone,
      dot: true,
      size: "sm"
    }, it.severidade), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 'var(--text-2xs)',
        color: 'var(--text-faint)'
      }
    }, it.categoria, " \xB7 ", it.origem))));
  })));
}

/* ===================== 04 — Situação Atual (donut + cards) ===================== */
function Donut({
  segments,
  total
}) {
  const R = 52,
    C = 2 * Math.PI * R;
  let offset = 0;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative',
      width: 150,
      height: 150,
      flex: 'none'
    }
  }, /*#__PURE__*/React.createElement("svg", {
    width: "150",
    height: "150",
    viewBox: "0 0 150 150"
  }, /*#__PURE__*/React.createElement("circle", {
    cx: "75",
    cy: "75",
    r: R,
    fill: "none",
    stroke: "var(--surface-muted)",
    strokeWidth: "18"
  }), segments.map((s, i) => {
    const len = s.value / total * C;
    const el = /*#__PURE__*/React.createElement("circle", {
      key: i,
      cx: "75",
      cy: "75",
      r: R,
      fill: "none",
      stroke: s.color,
      strokeWidth: "18",
      strokeDasharray: `${len} ${C - len}`,
      strokeDashoffset: -offset,
      transform: "rotate(-90 75 75)",
      strokeLinecap: "butt"
    });
    offset += len;
    return el;
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      inset: 0,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center'
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "aegis-tnum",
    style: {
      fontSize: 30,
      fontWeight: 800,
      color: 'var(--text-strong)',
      lineHeight: 1
    }
  }, total), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-2xs)',
      color: 'var(--text-muted)',
      fontWeight: 600,
      textTransform: 'uppercase',
      letterSpacing: '0.05em',
      marginTop: 3
    }
  }, "Sistemas")));
}
function SystemsStatus({
  items
}) {
  const M = window.REL_MAPS;
  const colorOf = {
    good: 'var(--good-foreground)',
    alert: 'var(--alert-foreground)',
    bad: 'var(--bad-foreground)'
  };
  const total = items.reduce((a, b) => a + b.quantidade, 0);
  const segments = items.map(it => ({
    value: it.quantidade,
    color: colorOf[it.status]
  }));
  return /*#__PURE__*/React.createElement(PanelCard, {
    id: "sec-situacao"
  }, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "gauge",
    iconTone: "heat",
    eyebrow: "04 \xB7 Distribui\xE7\xE3o",
    title: "Situa\xE7\xE3o Atual dos Sistemas",
    subtitle: "Distribui\xE7\xE3o dos sistemas conforme sua condi\xE7\xE3o operacional no per\xEDodo.",
    right: /*#__PURE__*/React.createElement(StatusLegend, null)
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '220px 1fr',
      gap: 22,
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: 16,
      padding: 8
    }
  }, /*#__PURE__*/React.createElement(Donut, {
    segments: segments,
    total: total
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 7,
      width: '100%'
    }
  }, items.map(it => /*#__PURE__*/React.createElement("div", {
    key: it.condicao,
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 7,
      fontSize: 'var(--text-xs)',
      color: 'var(--text-body)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 10,
      height: 10,
      borderRadius: 3,
      background: colorOf[it.status]
    }
  }), it.condicao), /*#__PURE__*/React.createElement("span", {
    className: "aegis-tnum",
    style: {
      fontSize: 'var(--text-sm)',
      fontWeight: 700,
      color: 'var(--text-strong)'
    }
  }, it.quantidade))))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))',
      gap: 14
    }
  }, items.map(it => {
    const c = colorOf[it.status];
    const soft = it.status === 'bad' ? 'var(--bad-background)' : it.status === 'alert' ? 'var(--alert-background)' : 'var(--good-background)';
    return /*#__PURE__*/React.createElement("div", {
      key: it.condicao,
      style: {
        display: 'flex',
        flexDirection: 'column',
        borderRadius: 'var(--radius-lg)',
        border: '1px solid var(--border-subtle)',
        overflow: 'hidden',
        background: 'var(--surface-card)'
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 10,
        padding: '13px 16px',
        background: soft
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        fontSize: 'var(--text-sm)',
        fontWeight: 700,
        color: c
      }
    }, /*#__PURE__*/React.createElement(RT.Icon, {
      name: M.STATUS_ICON[it.condicao],
      size: 16
    }), it.condicao), /*#__PURE__*/React.createElement("span", {
      className: "aegis-tnum",
      style: {
        fontSize: 26,
        fontWeight: 800,
        color: c,
        lineHeight: 1
      }
    }, it.quantidade)), /*#__PURE__*/React.createElement("div", {
      style: {
        padding: '13px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 12
      }
    }, /*#__PURE__*/React.createElement("p", {
      style: {
        fontSize: 'var(--text-xs)',
        color: 'var(--text-body)',
        lineHeight: 1.45
      }
    }, it.definicao), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 'var(--text-2xs)',
        fontWeight: 700,
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        color: 'var(--text-faint)',
        marginBottom: 5
      }
    }, "Locais atendidos"), it.locais.map((l, i) => /*#__PURE__*/React.createElement("div", {
      key: i,
      style: {
        fontSize: 'var(--text-xs)',
        color: 'var(--text-body)',
        lineHeight: 1.45
      }
    }, l))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 'var(--text-2xs)',
        fontWeight: 700,
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        color: 'var(--text-faint)',
        marginBottom: 5
      }
    }, "Riscos atuais"), it.riscos.map((r, i) => /*#__PURE__*/React.createElement("div", {
      key: i,
      style: {
        display: 'flex',
        gap: 7,
        fontSize: 'var(--text-xs)',
        color: 'var(--text-body)',
        lineHeight: 1.45,
        marginBottom: 3
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        color: c,
        flex: 'none',
        marginTop: 1
      }
    }, "\u2022"), r)))));
  }))));
}
Object.assign(window, {
  ReportCover,
  TeamSection,
  ConditionSection,
  SystemsStatus
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/relatorios/ReportTop.jsx", error: String((e && e.message) || e) }); }

// ui_kits/relatorios/data.js
try { (() => {
/* Mock data for the Relatórios UI kit (Relatório de Saúde dos Sistemas).
   In production these arrive from Supabase, scoped by tenant_id + RLS. */
window.AEGIS_REPORT = {
  tenant: {
    id: 'hersil',
    name: 'Hersil'
  },
  user: {
    name: 'Rodrigo Andrade',
    email: 'rodrigo@hersil.com.br',
    role: 'Admin'
  },
  /* --- Section 01 — Capa / Identificação --- */
  cover: {
    titulo: 'Relatório de Saúde dos Sistemas',
    subtitulo: 'Análise detalhada do desempenho e condições dos sistemas monitorados.',
    cliente: 'Hersil',
    site: 'Condomínio Edifício SP Tower',
    mesReferencia: 'Fevereiro de 2026',
    periodo: '01/02/2026 a 28/02/2026',
    codigo: 'REL-2026-02-0184',
    versao: 'v2.1',
    status: 'Publicado',
    dataEmissao: '03/03/2026',
    responsavel: 'Isaque Jordão'
  },
  /* --- Section 02 — Time Envolvido --- */
  team: [{
    funcao: 'Gestor',
    nome: 'Jairo Souza',
    empresa: 'Aegis Operações',
    email: 'jairo.souza@aegis.com.br',
    telefone: '+55 11 99812-4477',
    badge: 'Responsável geral'
  }, {
    funcao: 'Especialista',
    nome: 'Isaque Jordão',
    empresa: 'Aegis Engenharia',
    email: 'isaque.jordao@aegis.com.br',
    telefone: '+55 11 99745-2210',
    badge: 'Responsável técnico'
  }],
  /* --- Section 03 — Condição Geral da Climatização --- */
  condicaoGeral: [{
    texto: 'Aumento expressivo na reincidência de anomalias e alarmes no período.',
    severidade: 'Crítico',
    categoria: 'Reincidência',
    origem: 'Monitoramento contínuo',
    status: 'Aberto',
    icon: 'trending-up'
  }, {
    texto: 'Acúmulo de pendências não resolvidas de relatórios anteriores.',
    severidade: 'Ação Imediata',
    categoria: 'Pendências',
    origem: 'Histórico de relatórios',
    status: 'Aberto',
    icon: 'layers'
  }, {
    texto: 'Crescimento do número de conjuntos em risco de quebra.',
    severidade: 'Ação Imediata',
    categoria: 'Risco de quebra',
    origem: 'Análise preditiva',
    status: 'Aberto',
    icon: 'alert-triangle'
  }, {
    texto: 'Sistemas em estado crítico, incluindo renovação de ar e conjuntos.',
    severidade: 'Crítico',
    categoria: 'Estado crítico',
    origem: 'Inspeção técnica',
    status: 'Aberto',
    icon: 'thermometer-snowflake'
  }, {
    texto: 'Ações corretivas e preditivas necessárias para evitar agravamento.',
    severidade: 'Atenção',
    categoria: 'Plano de ação',
    origem: 'Recomendação técnica',
    status: 'Planejado',
    icon: 'wrench'
  }],
  /* --- Section 04 — Situação Atual dos Sistemas --- */
  situacaoAtual: [{
    condicao: 'Ação Imediata',
    quantidade: 13,
    status: 'bad',
    definicao: 'Sistema em risco de quebra severa, necessário ação imediata para correção.',
    locais: ['Conjunto 12, 31, 32, 51, 82, 91, 92, 112 e 132', 'Todos os sistemas de renovação'],
    riscos: ['Risco de quebra de compressores e placas eletrônicas', 'Risco de parada do sistema por falta de fluido']
  }, {
    condicao: 'Atenção',
    quantidade: 4,
    status: 'alert',
    definicao: 'Sistema operando com desvio prejudicando o rendimento e a vida útil.',
    locais: ['Conjunto 21, 52, 71 e 102'],
    riscos: ['Risco de queima de placas eletrônicas', 'Risco de perda de climatização de ambientes individuais']
  }, {
    condicao: 'Normal',
    quantidade: 13,
    status: 'good',
    definicao: 'Sistema sem anomalia.',
    locais: ['Todos os demais sistemas do prédio'],
    riscos: ['Operando sem apresentar anomalias atualmente']
  }],
  /* --- Section 05 — Principais Alarmes --- */
  alarmes: [{
    codigo: 'CH-23',
    criticidade: 'Alta',
    descricao: 'Baixa tensão',
    sistemas: ['Conjunto 32'],
    eventos: 8
  }, {
    codigo: 'CH-173',
    criticidade: 'Alta',
    descricao: 'Alta corrente do compressor fixo',
    sistemas: ['Conjunto 12'],
    eventos: 15
  }, {
    codigo: 'CH-04',
    criticidade: 'Média',
    descricao: 'Sistema de drenagem comprometido',
    sistemas: ['Conjunto 31', 'Conjunto 71', 'Conjunto 102'],
    eventos: 67
  }, {
    codigo: 'CH-03',
    criticidade: 'Baixa',
    descricao: 'Controle remoto de parede com defeito',
    sistemas: ['Conjunto 31'],
    eventos: 52
  }],
  /* --- Section 06 — Principais Anomalias --- */
  anomalias: [{
    codigo: '13',
    criticidade: 'Alta',
    descricao: 'Retorno de líquido ao compressor',
    sistemas: ['Renov. 11 ao 61', 'Renov. 12 ao 62'],
    eventos: 410
  }, {
    codigo: '42',
    criticidade: 'Alta',
    descricao: 'Evaporadora com passagem / sensor descalibrado',
    sistemas: ['Conjunto 31, 51 e 92', 'Renov. 11 ao 61 e 12 ao 62'],
    eventos: 121
  }, {
    codigo: '03',
    criticidade: 'Alta',
    descricao: 'Variação de tensão',
    sistemas: ['Conjunto 31, 51, 82, 91, 92, 112 e 132', 'Renov. 11 ao 61, 71 ao 131 e 72 ao 132'],
    eventos: 857
  }, {
    codigo: '16',
    criticidade: 'Média',
    descricao: 'Sensor danificado',
    sistemas: ['Conjunto 12, 21, 51, 52, 71 e 102'],
    eventos: 303
  }],
  /* --- Section 07 — Próximos Passos --- */
  proximosPassos: [{
    sistema: 'Renovação de ar',
    local: 'Conjunto 11 ao 61',
    condicao: 'Ação Imediata',
    prioridade: 'Alta',
    responsavel: 'Isaque Jordão',
    prazo: '10/03/2026',
    statusAcao: 'Pendente',
    riscos: ['Parada completa do sistema', 'Altos custos de correção'],
    acoes: ['Troca da placa eletrônica da evaporadora de ar externo do conjunto 21', 'Revisar a distribuição elétrica da concessionária e comunicar Enel']
  }, {
    sistema: 'Renovação de ar',
    local: 'Conjunto 12 ao 62',
    condicao: 'Ação Imediata',
    prioridade: 'Alta',
    responsavel: 'Isaque Jordão',
    prazo: '10/03/2026',
    statusAcao: 'Pendente',
    riscos: ['Parada completa do sistema', 'Altos custos de correção', 'Transtorno na operação', 'Perda de rendimento do sistema'],
    acoes: ['Troca da placa eletrônica da evaporadora de ar externo do conjunto 62', 'Troca do sensor da evaporadora AC_UNIT_E5']
  }, {
    sistema: 'Conjunto 12',
    local: '1º Andar',
    condicao: 'Ação Imediata',
    prioridade: 'Alta',
    responsavel: 'Equipe de campo',
    prazo: '12/03/2026',
    statusAcao: 'Em andamento',
    riscos: ['Parada completa do sistema', 'Altos custos de correção', 'Transtorno na operação', 'Perda de rendimento do sistema'],
    acoes: ['Revisar aperto das conexões do compressor fixo', 'Troca da pasta térmica da placa inverter', 'Troca do sensor da evaporadora AC_UNIT_54', 'Troca do sensor da evaporadora AC_UNIT_56']
  }, {
    sistema: 'Conjunto 31',
    local: '3º Andar',
    condicao: 'Ação Imediata',
    prioridade: 'Alta',
    responsavel: 'Equipe de campo',
    prazo: '12/03/2026',
    statusAcao: 'Pendente',
    riscos: ['Queima de compressores e placas eletrônicas', 'Parada completa do sistema', 'Altos custos de correção', 'Transtorno na operação', 'Perda de rendimento do sistema', 'Vazamento de água'],
    acoes: ['Troca do kit EEV da evaporadora AC_UNIT_04', 'Troca do kit EEV da evaporadora AC_UNIT_05', 'Troca do kit EEV da evaporadora AC_UNIT_06', 'Troca do controle da evaporadora AC_UNIT_06', 'Troca da bomba de dreno e limpeza do sistema de drenagem da evaporadora AC_UNIT_05', 'Revisar a distribuição elétrica da concessionária e comunicar Enel']
  }, {
    sistema: 'Conjunto 92',
    local: '9º Andar',
    condicao: 'Ação Imediata',
    prioridade: 'Média',
    responsavel: 'Equipe de campo',
    prazo: '15/03/2026',
    statusAcao: 'Pendente',
    riscos: ['Queima de compressores e placas eletrônicas', 'Transtorno na operação', 'Perda de rendimento do sistema'],
    acoes: ['Revisar a distribuição elétrica da concessionária e comunicar Enel', 'Troca do sensor da evaporadora AC_UNIT_76']
  }, {
    sistema: 'Conjunto 71',
    local: '7º Andar',
    condicao: 'Atenção',
    prioridade: 'Média',
    responsavel: 'Equipe de campo',
    prazo: '18/03/2026',
    statusAcao: 'Pendente',
    riscos: ['Transtorno na operação', 'Perda de rendimento do sistema', 'Vazamento de água'],
    acoes: ['Troca do sensor da evaporadora AC_UNIT_15', 'Troca da bomba de dreno e limpeza do sistema de drenagem da evaporadora AC_UNIT_16']
  }, {
    sistema: 'Conjunto 102',
    local: '10º Andar',
    condicao: 'Atenção',
    prioridade: 'Média',
    responsavel: 'Equipe de campo',
    prazo: '18/03/2026',
    statusAcao: 'Pendente',
    riscos: ['Transtorno na operação', 'Perda de rendimento do sistema', 'Vazamento de água'],
    acoes: ['Troca do sensor da evaporadora AC_UNIT_7B', 'Troca da bomba de dreno e limpeza do sistema de drenagem da evaporadora AC_UNIT_7C']
  }],
  /* --- Sections 08–10 — Matriz técnica --- */
  matrizCols: ['Pressões do Sistema', 'Carga de Fluido Refrigerante', 'Rendimento do Sistema', 'Elétrica', "Válvulas de Expansão EEV's", 'Funcionamento de Sensores', 'Preventiva'],
  matrizRisco: [{
    sistema: 'Renov. 11~61',
    cells: ['Ação Imediata', 'Atenção', 'Ação Imediata', 'Atenção', 'Ação Imediata', 'Atenção', 'Normal']
  }, {
    sistema: 'Renov. 12~62',
    cells: ['Ação Imediata', 'Atenção', 'Ação Imediata', 'Atenção', 'Ação Imediata', 'Atenção', 'Normal']
  }, {
    sistema: 'Renov. 71~131',
    cells: ['Atenção', 'Normal', 'Ação Imediata', 'Ação Imediata', 'Atenção', 'Atenção', 'Normal']
  }, {
    sistema: 'Renov. 72~132',
    cells: ['Atenção', 'Normal', 'Ação Imediata', 'Ação Imediata', 'Atenção', 'Atenção', 'Normal']
  }, {
    sistema: 'Conjunto 12',
    cells: ['Atenção', 'Normal', 'Atenção', 'Ação Imediata', 'Normal', 'Atenção', 'Atenção']
  }, {
    sistema: 'Conjunto 31',
    cells: ['Atenção', 'Normal', 'Ação Imediata', 'Atenção', 'Ação Imediata', 'Ação Imediata', 'Atenção']
  }, {
    sistema: 'Conjunto 32',
    cells: ['Ação Imediata', 'Normal', 'Atenção', 'Ação Imediata', 'Normal', 'Atenção', 'Normal']
  }, {
    sistema: 'Conjunto 51',
    cells: ['Atenção', 'Normal', 'Atenção', 'Atenção', 'Normal', 'Ação Imediata', 'Normal']
  }, {
    sistema: 'Conjunto 91',
    cells: ['Normal', 'Normal', 'Atenção', 'Ação Imediata', 'Normal', 'Atenção', 'Normal']
  }, {
    sistema: 'Conjunto 92',
    cells: ['Atenção', 'Normal', 'Atenção', 'Ação Imediata', 'Normal', 'Ação Imediata', 'Atenção']
  }, {
    sistema: 'Conjunto 111',
    cells: ['Normal', 'Normal', 'Atenção', 'Atenção', 'Normal', 'Atenção', 'Normal']
  }, {
    sistema: 'Conjunto 112',
    cells: ['Atenção', 'Normal', 'Ação Imediata', 'Ação Imediata', 'Normal', 'Atenção', 'Normal']
  }, {
    sistema: 'Conjunto 132',
    cells: ['Atenção', 'Normal', 'Ação Imediata', 'Ação Imediata', 'Normal', 'Atenção', 'Normal']
  }],
  comentariosRisco: ["Sistemas de renovação apresentaram anomalias de retorno de líquido para o compressor, afetando pressões, rendimento e funcionamento das EEV's.", 'Sistemas de renovação apresentaram baixa tensão, afetando o rendimento do sistema e gerando risco constante às placas e ao compressor.', 'Conjunto 31 apresentou anomalias relacionadas a evaporadora com passagem/sensor danificado nas evaporadoras AC_UNIT_04, AC_UNIT_05 e AC_UNIT_06.', 'Conjunto 31 também apresentou alarme CH-03, referente a controle remoto de parede com defeito na AC_UNIT_06.', 'Conjunto 92 apresentou anomalia referente à evaporadora com passagem/sensor descalibrado na evaporadora AC_UNIT_76.'],
  matrizAtencao: [{
    sistema: 'Conjunto 21',
    cells: ['Normal', 'Normal', 'Atenção', 'Normal', 'Normal', 'Atenção', 'Normal']
  }, {
    sistema: 'Conjunto 52',
    cells: ['Normal', 'Normal', 'Atenção', 'Normal', 'Atenção', 'Atenção', 'Normal']
  }, {
    sistema: 'Conjunto 71',
    cells: ['Normal', 'Normal', 'Atenção', 'Normal', 'Atenção', 'Ação Imediata', 'Atenção']
  }, {
    sistema: 'Conjunto 102',
    cells: ['Normal', 'Normal', 'Atenção', 'Normal', 'Atenção', 'Ação Imediata', 'Atenção']
  }],
  comentariosAtencao: ['Conjunto 21, Conjunto 52, Conjunto 71 e Conjunto 102 apresentaram anomalias referentes ao mau funcionamento dos sensores nas evaporadoras.', 'Conjunto 71 e Conjunto 102 apresentaram alarme CH-04 relacionado ao mau funcionamento do sistema de drenagem.', "As anomalias geram alerta em relação ao rendimento dos sistemas, funcionamento das EEV's e funcionamento dos sensores."],
  /* --- Section 12 — Resumo dos Sistemas --- */
  resumo: [{
    nome: 'Conjunto 11',
    local: '1º Andar',
    fab: 'LG',
    cap: '12 HP',
    evap: 6,
    modelo: 'Built-in',
    status: 'Normal'
  }, {
    nome: 'Conjunto 12',
    local: '1º Andar',
    fab: 'LG',
    cap: '16 HP',
    evap: 8,
    modelo: 'Built-in',
    status: 'Ação Imediata'
  }, {
    nome: 'Conjunto 21',
    local: '2º Andar',
    fab: 'LG',
    cap: '12 HP',
    evap: 6,
    modelo: 'Built-in',
    status: 'Atenção'
  }, {
    nome: 'Conjunto 22',
    local: '2º Andar',
    fab: 'LG',
    cap: '12 HP',
    evap: 6,
    modelo: 'Built-in',
    status: 'Normal'
  }, {
    nome: 'Conjunto 31',
    local: '3º Andar',
    fab: 'LG',
    cap: '16 HP',
    evap: 8,
    modelo: 'Built-in',
    status: 'Ação Imediata'
  }, {
    nome: 'Conjunto 32',
    local: '3º Andar',
    fab: 'LG',
    cap: '16 HP',
    evap: 8,
    modelo: 'Built-in',
    status: 'Ação Imediata'
  }, {
    nome: 'Conjunto 41',
    local: '4º Andar',
    fab: 'LG',
    cap: '12 HP',
    evap: 6,
    modelo: 'Built-in',
    status: 'Normal'
  }, {
    nome: 'Conjunto 42',
    local: '4º Andar',
    fab: 'LG',
    cap: '12 HP',
    evap: 6,
    modelo: 'Built-in',
    status: 'Normal'
  }, {
    nome: 'Conjunto 51',
    local: '5º Andar',
    fab: 'LG',
    cap: '16 HP',
    evap: 8,
    modelo: 'Built-in',
    status: 'Ação Imediata'
  }, {
    nome: 'Conjunto 52',
    local: '5º Andar',
    fab: 'LG',
    cap: '12 HP',
    evap: 6,
    modelo: 'Built-in',
    status: 'Atenção'
  }, {
    nome: 'Conjunto 61',
    local: '6º Andar',
    fab: 'LG',
    cap: '12 HP',
    evap: 6,
    modelo: 'Built-in',
    status: 'Normal'
  }, {
    nome: 'Conjunto 62',
    local: '6º Andar',
    fab: 'LG',
    cap: '12 HP',
    evap: 6,
    modelo: 'Built-in',
    status: 'Normal'
  }, {
    nome: 'Conjunto 71',
    local: '7º Andar',
    fab: 'LG',
    cap: '12 HP',
    evap: 6,
    modelo: 'Built-in',
    status: 'Atenção'
  }, {
    nome: 'Conjunto 72',
    local: '7º Andar',
    fab: 'LG',
    cap: '12 HP',
    evap: 6,
    modelo: 'Built-in',
    status: 'Normal'
  }, {
    nome: 'Conjunto 81',
    local: '8º Andar',
    fab: 'LG',
    cap: '12 HP',
    evap: 6,
    modelo: 'Built-in',
    status: 'Normal'
  }, {
    nome: 'Conjunto 82',
    local: '8º Andar',
    fab: 'LG',
    cap: '16 HP',
    evap: 8,
    modelo: 'Built-in',
    status: 'Ação Imediata'
  }, {
    nome: 'Conjunto 91',
    local: '9º Andar',
    fab: 'LG',
    cap: '16 HP',
    evap: 8,
    modelo: 'Built-in',
    status: 'Ação Imediata'
  }, {
    nome: 'Conjunto 92',
    local: '9º Andar',
    fab: 'LG',
    cap: '16 HP',
    evap: 8,
    modelo: 'Built-in',
    status: 'Ação Imediata'
  }, {
    nome: 'Conjunto 101',
    local: '10º Andar',
    fab: 'LG',
    cap: '12 HP',
    evap: 6,
    modelo: 'Built-in',
    status: 'Normal'
  }, {
    nome: 'Conjunto 102',
    local: '10º Andar',
    fab: 'LG',
    cap: '12 HP',
    evap: 6,
    modelo: 'Built-in',
    status: 'Atenção'
  }, {
    nome: 'Renov. 71~131',
    local: 'Cobertura',
    fab: 'LG',
    cap: '16 HP',
    evap: 8,
    modelo: 'Built-in',
    status: 'Ação Imediata'
  }, {
    nome: 'Renov. 72~132',
    local: 'Cobertura',
    fab: 'LG',
    cap: '16 HP',
    evap: 8,
    modelo: 'Built-in',
    status: 'Ação Imediata'
  }],
  /* --- Filter option sources --- */
  clients: [{
    label: 'Hersil',
    value: 'hersil'
  }, {
    label: 'ACME Energia',
    value: 'acme'
  }, {
    label: 'Vortex Telecom',
    value: 'vortex'
  }],
  sites: [{
    label: 'Condomínio Edifício SP Tower',
    value: 'sptower'
  }, {
    label: 'RJ Data Center',
    value: 'rj'
  }, {
    label: 'MG Planta 1',
    value: 'mg'
  }],
  meses: [{
    label: 'Fevereiro de 2026',
    value: '2026-02'
  }, {
    label: 'Janeiro de 2026',
    value: '2026-01'
  }, {
    label: 'Dezembro de 2025',
    value: '2025-12'
  }],
  gestores: ['Todos', 'Jairo Souza'],
  especialistas: ['Todos', 'Isaque Jordão'],
  sistemasOpt: ['Todos os sistemas', 'Renovação de ar', 'Conjuntos', 'Renov. 11~61'],
  statusSistema: ['Todos', 'Normal', 'Atenção', 'Ação Imediata'],
  condicaoOpt: ['Todas', 'Risco de quebra', 'Em atenção', 'Sem anomalia'],
  criticidadeOpt: ['Todas', 'Baixa', 'Média', 'Alta'],
  tipoOcorrencia: ['Todos', 'Alarme', 'Anomalia']
};
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/relatorios/data.js", error: String((e && e.message) || e) }); }

// ui_kits/visao-executiva/ChartTooltip.jsx
try { (() => {
/* Visão Executiva — cursor-following analytical tooltip.
   Driven by Dashboard state: tip = { visible, x, y, payload }. */
const {
  Icon: TTip_Icon
} = window.AegisDesignSystem_86ea41;
const SEV_TOK = {
  critico: {
    fg: 'var(--bad-foreground)',
    label: 'CRÍTICO'
  },
  moderado: {
    fg: 'var(--alert-foreground)',
    label: 'MODERADO'
  },
  leve: {
    fg: 'var(--good-foreground)',
    label: 'LEVE'
  }
};
function TTRow({
  label,
  value,
  strong
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'baseline',
      justifyContent: 'space-between',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)'
    }
  }, label), /*#__PURE__*/React.createElement("span", {
    className: "aegis-tnum",
    style: {
      fontSize: strong ? 'var(--text-sm)' : 'var(--text-xs)',
      fontWeight: strong ? 800 : 600,
      color: strong ? 'var(--brand-strong)' : 'var(--text-strong)'
    }
  }, value));
}
function TTDivider() {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      height: 1,
      background: 'var(--border-subtle)',
      margin: '9px 0'
    }
  });
}
function TTDist({
  dist
}) {
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "aegis-eyebrow",
    style: {
      marginBottom: 6
    }
  }, "Distribui\xE7\xE3o"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 5
    }
  }, ['critico', 'moderado', 'leve'].map(k => /*#__PURE__*/React.createElement("div", {
    key: k,
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      fontSize: 'var(--text-2xs)',
      fontWeight: 700,
      letterSpacing: '0.04em',
      color: SEV_TOK[k].fg
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 7,
      height: 7,
      borderRadius: '50%',
      background: SEV_TOK[k].fg
    }
  }), SEV_TOK[k].label), /*#__PURE__*/React.createElement("span", {
    className: "aegis-tnum",
    style: {
      fontSize: 'var(--text-xs)',
      fontWeight: 700,
      color: 'var(--text-strong)'
    }
  }, dist[k])))));
}
function TTTitle({
  children,
  sub
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: 2
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-sm)',
      fontWeight: 800,
      color: 'var(--text-strong)',
      letterSpacing: '-0.01em'
    }
  }, children), sub && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-2xs)',
      color: 'var(--text-faint)',
      marginTop: 1
    }
  }, sub));
}
function renderPayload(p) {
  if (!p) return null;
  if (p.type === 'site') {
    return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(TTTitle, null, p.title), /*#__PURE__*/React.createElement(TTDivider, null), /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        flexDirection: 'column',
        gap: 5
      }
    }, /*#__PURE__*/React.createElement(TTRow, {
      label: "Total de Ocorr\xEAncias",
      value: p.total,
      strong: true
    }), /*#__PURE__*/React.createElement(TTRow, {
      label: "% sobre o total",
      value: p.pctTotal + '%'
    }), /*#__PURE__*/React.createElement(TTRow, {
      label: "Posi\xE7\xE3o no ranking",
      value: `#${p.rank} de ${p.rankTotal}`
    })), /*#__PURE__*/React.createElement(TTDivider, null), /*#__PURE__*/React.createElement(TTDist, {
      dist: p.dist
    }));
  }
  if (p.type === 'pareto') {
    return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(TTTitle, {
      sub: p.mode === 'line' ? 'Linha acumulada' : 'Barra'
    }, p.title), /*#__PURE__*/React.createElement(TTDivider, null), /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        flexDirection: 'column',
        gap: 5
      }
    }, /*#__PURE__*/React.createElement(TTRow, {
      label: "Ocorr\xEAncias",
      value: p.total,
      strong: p.mode !== 'line'
    }), /*#__PURE__*/React.createElement(TTRow, {
      label: "% sobre o total",
      value: p.pctTotal + '%'
    }), /*#__PURE__*/React.createElement(TTRow, {
      label: "% acumulado",
      value: p.pctCum + '%',
      strong: p.mode === 'line'
    }), /*#__PURE__*/React.createElement(TTRow, {
      label: "Ranking",
      value: `#${p.rank}`
    })), /*#__PURE__*/React.createElement(TTDivider, null), /*#__PURE__*/React.createElement(TTDist, {
      dist: p.dist
    }));
  }
  if (p.type === 'trend') {
    return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(TTTitle, null, p.title), /*#__PURE__*/React.createElement(TTDivider, null), /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        flexDirection: 'column',
        gap: 5
      }
    }, /*#__PURE__*/React.createElement(TTRow, {
      label: "Ocorr\xEAncias em aberto",
      value: p.emAberto,
      strong: true
    }), /*#__PURE__*/React.createElement(TTRow, {
      label: "Novas no dia",
      value: (p.novas >= 0 ? '+' : '') + p.novas
    }), /*#__PURE__*/React.createElement(TTRow, {
      label: "Total no per\xEDodo",
      value: p.totalPeriodo
    }), /*#__PURE__*/React.createElement(TTRow, {
      label: "% do dia sobre o per\xEDodo",
      value: p.pctDia + '%'
    })), /*#__PURE__*/React.createElement(TTDivider, null), /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: 7,
        fontSize: 'var(--text-2xs)',
        color: 'var(--text-muted)'
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 18,
        height: 18,
        borderRadius: 5,
        background: 'var(--brand-soft)',
        color: 'var(--brand-strong)'
      }
    }, /*#__PURE__*/React.createElement(TTip_Icon, {
      name: "arrow-up-right",
      size: 12
    })), "M\xE1ximo: ", /*#__PURE__*/React.createElement("b", {
      className: "aegis-tnum",
      style: {
        color: 'var(--text-strong)'
      }
    }, p.max.valor), " em ", p.max.data));
  }
  if (p.type === 'treemap') {
    return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        flexDirection: 'column',
        gap: 1,
        marginBottom: 2
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 'var(--text-2xs)',
        color: 'var(--text-faint)'
      }
    }, "Site: ", /*#__PURE__*/React.createElement("b", {
      style: {
        color: 'var(--text-body)'
      }
    }, p.site)), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 'var(--text-sm)',
        fontWeight: 800,
        color: 'var(--text-strong)'
      }
    }, p.ambiente)), /*#__PURE__*/React.createElement(TTDivider, null), /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        flexDirection: 'column',
        gap: 5
      }
    }, /*#__PURE__*/React.createElement(TTRow, {
      label: "Ocorr\xEAncias",
      value: p.ocorrencias,
      strong: true
    }), /*#__PURE__*/React.createElement(TTRow, {
      label: "% do Site",
      value: p.pctSite + '%'
    }), /*#__PURE__*/React.createElement(TTRow, {
      label: "% do Total",
      value: p.pctTotal + '%'
    }), /*#__PURE__*/React.createElement(TTRow, {
      label: "N\xEDvel",
      value: p.nivel
    })), /*#__PURE__*/React.createElement(TTDivider, null), /*#__PURE__*/React.createElement(TTDist, {
      dist: p.dist
    }));
  }
  if (p.type === 'kpi') {
    return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(TTTitle, null, p.title), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 'var(--text-xs)',
        color: 'var(--text-body)',
        lineHeight: 1.5,
        marginTop: 6
      }
    }, p.text));
  }
  return null;
}
function ChartTooltip({
  tip
}) {
  const ref = React.useRef(null);
  const [pos, setPos] = React.useState({
    left: -9999,
    top: -9999
  });
  React.useLayoutEffect(() => {
    if (!tip.visible || !ref.current) return;
    const el = ref.current;
    const w = el.offsetWidth,
      h = el.offsetHeight;
    const pad = 14,
      gap = 16;
    let left = tip.x + gap;
    let top = tip.y + gap;
    if (left + w + pad > window.innerWidth) left = tip.x - w - gap;
    if (left < pad) left = pad;
    if (top + h + pad > window.innerHeight) top = tip.y - h - gap;
    if (top < pad) top = pad;
    setPos({
      left,
      top
    });
  }, [tip.visible, tip.x, tip.y, tip.payload]);
  React.useEffect(() => {
    if (window.lucide) window.lucide.createIcons();
  });
  if (!tip.visible) return null;
  return /*#__PURE__*/React.createElement("div", {
    ref: ref,
    style: {
      position: 'fixed',
      left: pos.left,
      top: pos.top,
      zIndex: 9000,
      pointerEvents: 'none',
      width: tip.payload && tip.payload.type === 'kpi' ? 240 : 232,
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--radius-lg)',
      boxShadow: 'var(--shadow-lg)',
      padding: '13px 15px',
      fontFamily: 'var(--font-sans)',
      opacity: pos.left < 0 ? 0 : 1,
      transition: 'opacity var(--duration-fast) var(--ease-standard)'
    }
  }, renderPayload(tip.payload));
}
Object.assign(window, {
  ChartTooltip
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/visao-executiva/ChartTooltip.jsx", error: String((e && e.message) || e) }); }

// ui_kits/visao-executiva/Charts.jsx
try { (() => {
/* Visão Executiva — chart primitives (responsive SVG/DOM).
   Colours from the Aegis categorical / heatmap tokens.
   Interactivity: onHover(payload, evt) · onLeave() · onDrill({filterType,value}). */

const CAT = ['var(--categorical-4)', 'var(--categorical-3)', 'var(--categorical-2)', 'var(--categorical-1)', 'var(--categorical-5)', 'var(--categorical-6)', 'var(--categorical-7)', 'var(--categorical-8)'];
const noop = () => {};

/* ---------------- Horizontal bar chart ---------------- */
function BarChartH({
  data,
  onHover = noop,
  onLeave = noop,
  onDrill = noop
}) {
  const max = Math.max(...data.map(d => d.value));
  const total = data.reduce((s, d) => s + d.value, 0);
  const ranked = [...data].sort((a, b) => b.value - a.value);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 16,
      paddingTop: 4
    }
  }, data.map((d, i) => {
    const payload = {
      type: 'site',
      title: d.name,
      total: d.value,
      pctTotal: (d.value / total * 100).toFixed(1),
      rank: ranked.findIndex(x => x.name === d.name) + 1,
      rankTotal: data.length,
      dist: d.dist || {
        critico: 0,
        moderado: 0,
        leve: 0
      }
    };
    return /*#__PURE__*/React.createElement("div", {
      key: d.name,
      onMouseEnter: e => onHover(payload, e),
      onMouseMove: e => onHover(payload, e),
      onMouseLeave: onLeave,
      onClick: () => onDrill({
        filterType: 'site',
        value: d.name
      }),
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        cursor: 'pointer'
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        width: 110,
        flex: 'none',
        fontSize: 'var(--text-sm)',
        color: 'var(--text-body)',
        fontWeight: 500,
        textAlign: 'right'
      }
    }, d.name), /*#__PURE__*/React.createElement("div", {
      style: {
        flex: 1,
        height: 22,
        background: 'var(--surface-muted)',
        borderRadius: 'var(--radius-pill)',
        overflow: 'hidden'
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        width: `${Math.max(d.value / max * 100, 4)}%`,
        height: '100%',
        background: CAT[i % 4],
        borderRadius: 'var(--radius-pill)',
        transition: 'width 600ms var(--ease-out)'
      }
    })), /*#__PURE__*/React.createElement("span", {
      className: "aegis-tnum",
      style: {
        width: 30,
        flex: 'none',
        fontSize: 'var(--text-sm)',
        fontWeight: 700,
        color: 'var(--text-strong)'
      }
    }, d.value));
  }));
}

/* ---------------- Pareto: bars + cumulative line ---------------- */
function ParetoChart({
  data,
  onHover = noop,
  onLeave = noop,
  onDrill = noop
}) {
  const W = 520,
    H = 230,
    padL = 34,
    padR = 38,
    padT = 16,
    padB = 34;
  const iw = W - padL - padR,
    ih = H - padT - padB;
  const total = data.reduce((s, d) => s + d.value, 0);
  const max = Math.max(...data.map(d => d.value));
  const bw = iw / data.length;
  let cum = 0;
  const pts = data.map((d, i) => {
    cum += d.value;
    const x = padL + bw * i + bw / 2;
    const y = padT + ih - cum / total * ih;
    return {
      x,
      y,
      pctCum: (cum / total * 100).toFixed(1)
    };
  });
  const linePath = pts.map((p, i) => `${i ? 'L' : 'M'}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
  const yticks = [0, 0.25, 0.5, 0.75, 1];
  const mk = (d, i, mode) => ({
    type: 'pareto',
    title: d.name,
    total: d.value,
    mode,
    pctTotal: (d.value / total * 100).toFixed(1),
    pctCum: pts[i].pctCum,
    rank: i + 1,
    dist: d.dist || {
      critico: 0,
      moderado: 0,
      leve: 0
    }
  });
  return /*#__PURE__*/React.createElement("svg", {
    viewBox: `0 0 ${W} ${H}`,
    width: "100%",
    style: {
      display: 'block',
      overflow: 'visible'
    }
  }, yticks.map((t, i) => {
    const y = padT + ih - t * ih;
    return /*#__PURE__*/React.createElement("g", {
      key: i
    }, /*#__PURE__*/React.createElement("line", {
      x1: padL,
      y1: y,
      x2: padL + iw,
      y2: y,
      style: {
        stroke: 'var(--grid-line)'
      },
      strokeWidth: "1"
    }), /*#__PURE__*/React.createElement("text", {
      x: padL - 6,
      y: y + 3,
      textAnchor: "end",
      style: {
        fill: 'var(--text-faint)',
        fontSize: 9,
        fontFamily: 'var(--font-mono)'
      }
    }, Math.round(t * max)), /*#__PURE__*/React.createElement("text", {
      x: padL + iw + 6,
      y: y + 3,
      textAnchor: "start",
      style: {
        fill: 'var(--text-faint)',
        fontSize: 9,
        fontFamily: 'var(--font-mono)'
      }
    }, Math.round(t * 100), "%"));
  }), data.map((d, i) => {
    const h = d.value / max * ih;
    const x = padL + bw * i + bw * 0.18;
    return /*#__PURE__*/React.createElement("g", {
      key: d.name,
      style: {
        cursor: 'pointer'
      },
      onMouseEnter: e => onHover(mk(d, i, 'bar'), e),
      onMouseMove: e => onHover(mk(d, i, 'bar'), e),
      onMouseLeave: onLeave,
      onClick: () => onDrill({
        filterType: 'categoria',
        value: d.name
      })
    }, /*#__PURE__*/React.createElement("rect", {
      x: padL + bw * i,
      y: padT,
      width: bw,
      height: ih,
      fill: "transparent"
    }), /*#__PURE__*/React.createElement("rect", {
      x: x,
      y: padT + ih - h,
      width: bw * 0.64,
      height: h,
      rx: "4",
      style: {
        fill: CAT[Math.min(1 + i, 4)]
      }
    }), /*#__PURE__*/React.createElement("text", {
      x: padL + bw * i + bw / 2,
      y: H - padB + 14,
      textAnchor: "middle",
      style: {
        fill: 'var(--text-muted)',
        fontSize: 9
      }
    }, d.name.length > 8 ? d.name.slice(0, 7) + '…' : d.name));
  }), /*#__PURE__*/React.createElement("path", {
    d: linePath,
    fill: "none",
    style: {
      stroke: 'var(--categorical-4)'
    },
    strokeWidth: "2",
    strokeLinejoin: "round"
  }), pts.map((p, i) => /*#__PURE__*/React.createElement("g", {
    key: i,
    style: {
      cursor: 'pointer'
    },
    onMouseEnter: e => onHover(mk(data[i], i, 'line'), e),
    onMouseMove: e => onHover(mk(data[i], i, 'line'), e),
    onMouseLeave: onLeave,
    onClick: () => onDrill({
      filterType: 'categoria',
      value: data[i].name
    })
  }, /*#__PURE__*/React.createElement("circle", {
    cx: p.x,
    cy: p.y,
    r: "9",
    fill: "transparent"
  }), /*#__PURE__*/React.createElement("circle", {
    cx: p.x,
    cy: p.y,
    r: "3.5",
    style: {
      fill: 'var(--categorical-5)',
      stroke: 'var(--surface-card)'
    },
    strokeWidth: "1.5"
  }))));
}

/* ---------------- Trend line chart ---------------- */
function TrendChart({
  data,
  onHover = noop,
  onLeave = noop,
  onDrill = noop
}) {
  const W = 1040,
    H = 240,
    padL = 36,
    padR = 20,
    padT = 18,
    padB = 30;
  const iw = W - padL - padR,
    ih = H - padT - padB;
  const [active, setActive] = React.useState(null);
  const max = Math.max(...data.map(d => d.v)) * 1.1;
  const min = Math.min(...data.map(d => d.v)) * 0.85;
  const xx = i => padL + iw * i / (data.length - 1);
  const yy = v => padT + ih - (v - min) / (max - min) * ih;
  const line = data.map((d, i) => `${i ? 'L' : 'M'}${xx(i).toFixed(1)} ${yy(d.v).toFixed(1)}`).join(' ');
  const area = `${line} L${xx(data.length - 1).toFixed(1)} ${padT + ih} L${padL} ${padT + ih} Z`;
  const totalPeriodo = data.reduce((s, d) => s + (d.nova || 0), 0);
  const maxPt = data.reduce((m, d) => d.v > m.v ? d : m, data[0]);
  const mk = d => ({
    type: 'trend',
    title: d.d,
    emAberto: d.v,
    novas: d.nova || 0,
    totalPeriodo,
    pctDia: ((d.nova || 0) / totalPeriodo * 100).toFixed(1),
    max: {
      valor: maxPt.v,
      data: maxPt.d
    }
  });
  return /*#__PURE__*/React.createElement("svg", {
    viewBox: `0 0 ${W} ${H}`,
    width: "100%",
    style: {
      display: 'block'
    },
    preserveAspectRatio: "none"
  }, /*#__PURE__*/React.createElement("defs", null, /*#__PURE__*/React.createElement("linearGradient", {
    id: "trendfill",
    x1: "0",
    y1: "0",
    x2: "0",
    y2: "1"
  }, /*#__PURE__*/React.createElement("stop", {
    offset: "0%",
    style: {
      stopColor: 'var(--categorical-4)'
    },
    stopOpacity: "0.22"
  }), /*#__PURE__*/React.createElement("stop", {
    offset: "100%",
    style: {
      stopColor: 'var(--categorical-4)'
    },
    stopOpacity: "0"
  }))), Array.from({
    length: 5
  }).map((_, i) => {
    const v = min + (max - min) * i / 4;
    const y = yy(v);
    return /*#__PURE__*/React.createElement("g", {
      key: i
    }, /*#__PURE__*/React.createElement("line", {
      x1: padL,
      y1: y,
      x2: padL + iw,
      y2: y,
      style: {
        stroke: 'var(--grid-line)'
      },
      strokeWidth: "1"
    }), /*#__PURE__*/React.createElement("text", {
      x: padL - 8,
      y: y + 3,
      textAnchor: "end",
      style: {
        fill: 'var(--text-faint)',
        fontSize: 10,
        fontFamily: 'var(--font-mono)'
      }
    }, Math.round(v)));
  }), /*#__PURE__*/React.createElement("path", {
    d: area,
    fill: "url(#trendfill)"
  }), /*#__PURE__*/React.createElement("path", {
    d: line,
    fill: "none",
    style: {
      stroke: 'var(--categorical-4)'
    },
    strokeWidth: "2.5",
    strokeLinejoin: "round",
    strokeLinecap: "round"
  }), active != null && /*#__PURE__*/React.createElement("line", {
    x1: xx(active),
    y1: padT,
    x2: xx(active),
    y2: padT + ih,
    style: {
      stroke: 'var(--categorical-4)'
    },
    strokeWidth: "1",
    strokeDasharray: "4 4",
    opacity: "0.55"
  }), data.map((d, i) => /*#__PURE__*/React.createElement("g", {
    key: i
  }, /*#__PURE__*/React.createElement("circle", {
    cx: xx(i),
    cy: yy(d.v),
    r: active === i ? 5.5 : 3.5,
    style: {
      fill: 'var(--categorical-5)',
      stroke: 'var(--surface-card)'
    },
    strokeWidth: "2"
  }), /*#__PURE__*/React.createElement("text", {
    x: xx(i),
    y: H - 10,
    textAnchor: "middle",
    style: {
      fill: active === i ? 'var(--text-strong)' : 'var(--text-muted)',
      fontSize: 10,
      fontWeight: active === i ? 700 : 400
    }
  }, d.d), /*#__PURE__*/React.createElement("rect", {
    x: xx(i) - iw / (data.length - 1) / 2,
    y: padT,
    width: iw / (data.length - 1),
    height: ih,
    fill: "transparent",
    style: {
      cursor: 'pointer'
    },
    onMouseEnter: e => {
      setActive(i);
      onHover(mk(d), e);
    },
    onMouseMove: e => onHover(mk(d), e),
    onMouseLeave: () => {
      setActive(null);
      onLeave();
    },
    onClick: () => onDrill({
      filterType: 'data',
      value: d.d
    })
  }))));
}

/* ---------------- Treemap (squarified split) ---------------- */
function heatColor(t) {
  const stops = [[220, 255, 220],
  // #DCFFDC Baixa
  [255, 246, 230],
  // #FFF6E6 Média
  [255, 204, 204] // #FFCCCC Alta
  ];
  const seg = t < 0.5 ? 0 : 1;
  const lt = t < 0.5 ? t / 0.5 : (t - 0.5) / 0.5;
  const a = stops[seg],
    b = stops[seg + 1];
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * lt));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}
function splitTreemap(items, x, y, w, h, out) {
  if (!items.length) return;
  if (items.length === 1) {
    out.push({
      ...items[0],
      x,
      y,
      w,
      h
    });
    return;
  }
  const total = items.reduce((s, d) => s + d.value, 0);
  let run = 0,
    best = Infinity,
    splitAt = 1;
  for (let i = 0; i < items.length - 1; i++) {
    run += items[i].value;
    const diff = Math.abs(run - total / 2);
    if (diff < best) {
      best = diff;
      splitAt = i + 1;
    }
  }
  const a = items.slice(0, splitAt),
    b = items.slice(splitAt);
  const frac = a.reduce((s, d) => s + d.value, 0) / total;
  if (w >= h) {
    splitTreemap(a, x, y, w * frac, h, out);
    splitTreemap(b, x + w * frac, y, w * (1 - frac), h, out);
  } else {
    splitTreemap(a, x, y, w, h * frac, out);
    splitTreemap(b, x, y + h * frac, w, h * (1 - frac), out);
  }
}
function Treemap({
  data,
  width = 1040,
  height = 260,
  onHover = noop,
  onLeave = noop,
  onDrill = noop
}) {
  const max = Math.max(...data.map(d => d.value));
  const min = Math.min(...data.map(d => d.value));
  const total = data.reduce((s, d) => s + d.value, 0);
  const siteTotals = {};
  data.forEach(d => {
    siteTotals[d.site] = (siteTotals[d.site] || 0) + d.value;
  });
  const sorted = [...data].sort((a, b) => b.value - a.value);
  const rects = [];
  splitTreemap(sorted, 0, 0, width, height, rects);
  const gap = 4;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative',
      width: '100%',
      aspectRatio: `${width} / ${height}`
    }
  }, rects.map((r, i) => {
    const t = max === min ? 0.5 : (r.value - min) / (max - min);
    const big = r.w / width * 100 > 14 && r.h / height * 100 > 18;
    const pctTotal = (r.value / total * 100).toFixed(1);
    const nivel = pctTotal >= 25 ? 'Alta concentração' : pctTotal >= 12 ? 'Média concentração' : 'Baixa concentração';
    const payload = {
      type: 'treemap',
      site: r.site,
      ambiente: r.ambiente || r.name,
      ocorrencias: r.value,
      pctSite: (r.value / (siteTotals[r.site] || r.value) * 100).toFixed(1),
      pctTotal,
      nivel,
      dist: r.dist || {
        critico: 0,
        moderado: 0,
        leve: 0
      }
    };
    return /*#__PURE__*/React.createElement("div", {
      key: i,
      onMouseEnter: e => onHover(payload, e),
      onMouseMove: e => onHover(payload, e),
      onMouseLeave: onLeave,
      onClick: () => onDrill({
        filterType: 'bloco',
        value: r.name
      }),
      style: {
        position: 'absolute',
        left: `${r.x / width * 100}%`,
        top: `${r.y / height * 100}%`,
        width: `calc(${r.w / width * 100}% - ${gap}px)`,
        height: `calc(${r.h / height * 100}% - ${gap}px)`,
        background: heatColor(t),
        borderRadius: 'var(--radius-md)',
        border: '1px solid rgba(17,29,45,0.10)',
        padding: 12,
        color: '#27313F',
        overflow: 'hidden',
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        transition: 'transform var(--duration-fast) var(--ease-standard), box-shadow var(--duration-fast)'
      },
      onMouseOver: e => {
        e.currentTarget.style.boxShadow = 'var(--shadow-md)';
      },
      onMouseOut: e => {
        e.currentTarget.style.boxShadow = 'none';
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: big ? 'var(--text-sm)' : 'var(--text-2xs)',
        fontWeight: 600,
        opacity: 0.92,
        lineHeight: 1.2
      }
    }, r.name), /*#__PURE__*/React.createElement("span", {
      className: "aegis-tnum",
      style: {
        fontSize: big ? 'var(--text-2xl)' : 'var(--text-md)',
        fontWeight: 800,
        lineHeight: 1
      }
    }, r.value));
  }));
}
Object.assign(window, {
  BarChartH,
  ParetoChart,
  TrendChart,
  Treemap,
  heatColor
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/visao-executiva/Charts.jsx", error: String((e && e.message) || e) }); }

// ui_kits/visao-executiva/Dashboard.jsx
try { (() => {
/* Visão Executiva — main dashboard composition */
const DS = window.AegisDesignSystem_86ea41;
function PanelCard({
  children,
  style
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      background: 'var(--surface-card)',
      border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-xl)',
      boxShadow: 'var(--shadow-sm)',
      padding: 'var(--space-5)',
      ...style
    }
  }, children);
}
function PanelHead({
  icon,
  iconTone,
  eyebrow,
  title,
  subtitle,
  right
}) {
  const tones = {
    brand: ['var(--brand-soft)', 'var(--brand-strong)'],
    violet: ['rgba(31,122,138,0.14)', 'var(--accent-violet)'],
    amber: ['var(--alert-background)', 'var(--alert-foreground)'],
    heat: ['rgba(255,140,0,0.14)', 'var(--brand-strong)']
  }[iconTone] || ['var(--brand-soft)', 'var(--brand-strong)'];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'flex-start',
      justifyContent: 'space-between',
      gap: 16,
      marginBottom: 20
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      minWidth: 0
    }
  }, icon && /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 38,
      height: 38,
      flex: 'none',
      borderRadius: 'var(--radius-lg)',
      background: tones[0],
      color: tones[1]
    }
  }, /*#__PURE__*/React.createElement(DS.Icon, {
    name: icon,
    size: 19
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, eyebrow && /*#__PURE__*/React.createElement("div", {
    className: "aegis-eyebrow",
    style: {
      marginBottom: 3
    }
  }, eyebrow), /*#__PURE__*/React.createElement("h3", {
    style: {
      fontSize: 'var(--text-lg)',
      fontWeight: 700,
      color: 'var(--text-strong)',
      lineHeight: 1.2
    }
  }, title), subtitle && /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)',
      marginTop: 3
    }
  }, subtitle))), right && /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 'none'
    }
  }, right));
}
function HeatLegend() {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 14
    }
  }, [['Baixa', 'var(--heat-minimum)'], ['Média', 'var(--heat-center)'], ['Alta', 'var(--heat-maximum)']].map(([l, c]) => /*#__PURE__*/React.createElement("span", {
    key: l,
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)',
      fontWeight: 500
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 11,
      height: 11,
      borderRadius: 3,
      background: c
    }
  }), " ", l)));
}
function Dashboard({
  onNavigate
} = {}) {
  const D = window.AEGIS_DATA;
  const [dark, setDark] = React.useState(() => {
    try {
      return localStorage.getItem('aegis-theme') === 'dark';
    } catch (e) {
      return false;
    }
  });
  const [active, setActive] = React.useState('exec');
  const [collapsed, setCollapsed] = React.useState(false);
  const [trendP, setTrendP] = React.useState('30d');
  const [expA, setExpA] = React.useState('30d');
  const [expB, setExpB] = React.useState('30d');
  const [tip, setTip] = React.useState({
    visible: false,
    x: 0,
    y: 0,
    payload: null
  });
  const [drawer, setDrawer] = React.useState({
    open: false,
    data: null
  });
  const onHover = (payload, e) => setTip({
    visible: true,
    x: e.clientX,
    y: e.clientY,
    payload
  });
  const onLeave = () => setTip(t => ({
    ...t,
    visible: false
  }));
  const onDrill = ({
    filterType,
    value,
    extra
  }) => {
    setTip(t => ({
      ...t,
      visible: false
    }));
    setDrawer({
      open: true,
      data: D.drilldown(filterType, value, extra)
    });
  };
  const closeDrawer = () => setDrawer(s => ({
    ...s,
    open: false
  }));
  const kpiH = (title, info, drill) => ({
    onMouseEnter: e => onHover({
      type: 'kpi',
      title,
      text: info
    }, e),
    onMouseMove: e => onHover({
      type: 'kpi',
      title,
      text: info
    }, e),
    onMouseLeave: onLeave,
    ...(drill ? {
      onClick: () => onDrill(drill),
      style: {
        cursor: 'pointer'
      }
    } : {})
  });
  React.useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
    try {
      localStorage.setItem('aegis-theme', dark ? 'dark' : 'light');
    } catch (e) {}
  }, [dark]);
  React.useEffect(() => {
    if (window.lucide) window.lucide.createIcons();
  });
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      height: '100vh',
      overflow: 'hidden',
      background: 'var(--surface-app)'
    }
  }, /*#__PURE__*/React.createElement(window.Sidebar, {
    active: active,
    onNavigate: id => {
      if (id === 'reports' && onNavigate) onNavigate('reports');else setActive(id);
    },
    collapsed: collapsed,
    onToggle: () => setCollapsed(c => !c),
    user: D.user
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0,
      height: '100vh',
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement(window.Header, {
    dark: dark,
    onToggleTheme: setDark,
    user: D.user,
    tenant: D.tenant
  }), /*#__PURE__*/React.createElement("main", {
    style: {
      flex: 1,
      minHeight: 0,
      overflowY: 'auto',
      overflowX: 'hidden',
      padding: '24px 28px',
      display: 'flex',
      flexDirection: 'column',
      gap: 18
    }
  }, /*#__PURE__*/React.createElement(window.FilterBar, {
    data: D
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(4, 1fr)',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement("div", kpiH('Total de Ocorrências', D.kpiInfo.total), /*#__PURE__*/React.createElement(DS.KpiCard, {
    title: "Total de Ocorr\xEAncias",
    value: D.kpis.total,
    caption: "Todos os registros",
    icon: "file-text",
    accent: "brand"
  })), /*#__PURE__*/React.createElement("div", kpiH('Alarmes Ativos', D.kpiInfo.alarms, {
    filterType: 'kpi',
    value: 'Alarmes Ativos',
    extra: {
      total: D.kpis.alarms
    }
  }), /*#__PURE__*/React.createElement(DS.KpiCard, {
    title: "Alarmes Ativos",
    value: D.kpis.alarms,
    caption: "ALARMES em aberto",
    icon: "bell-ring",
    accent: "alert"
  })), /*#__PURE__*/React.createElement("div", kpiH('Anomalias Ativas', D.kpiInfo.anomalies, {
    filterType: 'kpi',
    value: 'Anomalias Ativas',
    extra: {
      total: D.kpis.anomalies
    }
  }), /*#__PURE__*/React.createElement(DS.KpiCard, {
    title: "Anomalias Ativas",
    value: D.kpis.anomalies,
    caption: "ANOMALIAS em aberto",
    icon: "activity",
    accent: "violet"
  })), /*#__PURE__*/React.createElement("div", kpiH('Ocorrências Críticas', D.kpiInfo.critical, {
    filterType: 'kpi',
    value: 'Ocorrências Críticas',
    extra: {
      total: D.kpis.critical
    }
  }), /*#__PURE__*/React.createElement(DS.KpiCard, {
    title: "Ocorr\xEAncias Cr\xEDticas",
    value: D.kpis.critical,
    caption: "CR\xCDTICO em aberto",
    icon: "flame",
    accent: "bad"
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(2, 1fr)',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement("div", kpiH('Exposição Média a Anomalias', D.kpiInfo.expAnomalies), /*#__PURE__*/React.createElement(DS.ExposureCard, {
    title: "Exposi\xE7\xE3o M\xE9dia a Anomalias",
    value: D.kpis.expAnomalies,
    caption: "Tempo m\xE9dio de ocorr\xEAncia nos \xFAltimos 30 dias",
    period: expA,
    onPeriodChange: setExpA,
    accent: "violet"
  })), /*#__PURE__*/React.createElement("div", kpiH('Exposição Média a Alarmes', D.kpiInfo.expAlarms), /*#__PURE__*/React.createElement(DS.ExposureCard, {
    title: "Exposi\xE7\xE3o M\xE9dia a Alarmes",
    value: D.kpis.expAlarms,
    caption: "Tempo m\xE9dio de ocorr\xEAncia nos \xFAltimos 30 dias",
    period: expB,
    onPeriodChange: setExpB,
    accent: "amber"
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement(PanelCard, null, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "bar-chart-3",
    iconTone: "brand",
    eyebrow: "Distribui\xE7\xE3o",
    title: "Ocorr\xEAncias por Site"
  }), /*#__PURE__*/React.createElement(window.BarChartH, {
    data: D.bySite,
    onHover: onHover,
    onLeave: onLeave,
    onDrill: onDrill
  })), /*#__PURE__*/React.createElement(PanelCard, null, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "chart-no-axes-combined",
    iconTone: "violet",
    eyebrow: "80 / 20",
    title: "Pareto de Ocorr\xEAncias por Categoria",
    right: /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        gap: 12
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        fontSize: 'var(--text-xs)',
        color: 'var(--text-muted)'
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        width: 11,
        height: 11,
        borderRadius: 3,
        background: 'var(--categorical-3)'
      }
    }), "Ocorr\xEAncias"), /*#__PURE__*/React.createElement("span", {
      style: {
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        fontSize: 'var(--text-xs)',
        color: 'var(--text-muted)'
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        width: 14,
        height: 3,
        borderRadius: 3,
        background: 'var(--categorical-4)'
      }
    }), "Acumulado"))
  }), /*#__PURE__*/React.createElement(window.ParetoChart, {
    data: D.pareto,
    onHover: onHover,
    onLeave: onLeave,
    onDrill: onDrill
  }))), /*#__PURE__*/React.createElement(PanelCard, null, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "trending-up",
    iconTone: "brand",
    eyebrow: "Em aberto",
    title: "Tend\xEAncia de Ocorr\xEAncias em Aberto",
    subtitle: "Evolu\xE7\xE3o di\xE1ria do total de ocorr\xEAncias em aberto ao longo do tempo \u2014 \xDAltimos 30d",
    right: /*#__PURE__*/React.createElement(DS.SegmentedControl, {
      options: ['7d', '15d', '30d', '60d', '90d'],
      value: trendP,
      onChange: setTrendP,
      size: "sm"
    })
  }), /*#__PURE__*/React.createElement(window.TrendChart, {
    data: D.trend,
    onHover: onHover,
    onLeave: onLeave,
    onDrill: onDrill
  })), /*#__PURE__*/React.createElement(PanelCard, null, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "grid-2x2",
    iconTone: "heat",
    eyebrow: "Densidade",
    title: "Mapa de Calor de Ocorr\xEAncias por Site e Ambiente",
    right: /*#__PURE__*/React.createElement(HeatLegend, null)
  }), /*#__PURE__*/React.createElement(window.Treemap, {
    data: D.treemap,
    onHover: onHover,
    onLeave: onLeave,
    onDrill: onDrill
  })), /*#__PURE__*/React.createElement(window.OccurrencesTable, {
    rows: D.occurrences
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 8
    }
  }))), /*#__PURE__*/React.createElement(window.ChartTooltip, {
    tip: tip
  }), /*#__PURE__*/React.createElement(window.Drawer, {
    open: drawer.open,
    data: drawer.data,
    onClose: closeDrawer,
    onClear: closeDrawer
  }));
}
Object.assign(window, {
  Dashboard
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/visao-executiva/Dashboard.jsx", error: String((e && e.message) || e) }); }

// ui_kits/visao-executiva/Drawer.jsx
try { (() => {
/* Visão Executiva — right-side drill-down drawer with overlay. */
const {
  Icon: DWIcon,
  Badge: DWBadge,
  Button: DWButton,
  IconButton: DWIconButton
} = window.AegisDesignSystem_86ea41;
const SEV_TONE = {
  'Crítica': 'bad',
  'Alta': 'alert',
  'Moderada': 'alert',
  'Leve': 'good',
  'Normal': 'good'
};
const STATUS_TONE = {
  'Aberto': 'bad',
  'Em tratamento': 'alert',
  'Resolvido': 'good',
  'Fechado': 'good'
};
function Skeleton({
  w = '100%',
  h = 14
}) {
  return /*#__PURE__*/React.createElement("span", {
    className: "aegis-skel",
    style: {
      display: 'block',
      width: w,
      height: h,
      borderRadius: 6,
      background: 'var(--surface-muted)'
    }
  });
}
function DrawerEmpty({
  onClear
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 14,
      padding: '60px 24px',
      textAlign: 'center'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 56,
      height: 56,
      borderRadius: 'var(--radius-xl)',
      background: 'var(--surface-muted)',
      color: 'var(--text-faint)'
    }
  }, /*#__PURE__*/React.createElement(DWIcon, {
    name: "inbox",
    size: 26
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-base)',
      fontWeight: 600,
      color: 'var(--text-strong)'
    }
  }, "Nenhuma ocorr\xEAncia encontrada"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-muted)',
      maxWidth: 280
    }
  }, "N\xE3o h\xE1 registros para este filtro no per\xEDodo selecionado."), /*#__PURE__*/React.createElement(DWButton, {
    variant: "secondary",
    size: "sm",
    icon: "eraser",
    onClick: onClear
  }, "Limpar filtro"));
}
function RowDetail({
  r
}) {
  const fields = [['Abertura', r.open], ['Atualização', r.upd], ['Equipamento', r.equip], ['Sistema', r.sistema], ['Severidade', r.sev], ['Status', r.status]];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      background: 'var(--surface-muted)',
      borderRadius: 'var(--radius-md)',
      padding: '12px 14px',
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: '8px 18px',
      margin: '0 0 4px'
    }
  }, fields.map(([k, v]) => /*#__PURE__*/React.createElement("div", {
    key: k,
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 1
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "aegis-eyebrow"
  }, k), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-strong)',
      fontWeight: 500
    }
  }, v))));
}
function DrawerDetail({
  r,
  onBack
}) {
  const fields = [['Código', r.id], ['Tipo', r.tipo], ['Local', r.local], ['Equipamento', r.equip], ['Sistema', r.sistema], ['Abertura', r.open], ['Atualização', r.upd]];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '18px 22px'
    }
  }, /*#__PURE__*/React.createElement("button", {
    onClick: onBack,
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      border: 'none',
      background: 'transparent',
      cursor: 'pointer',
      color: 'var(--brand-strong)',
      fontSize: 'var(--text-sm)',
      fontWeight: 600,
      fontFamily: 'var(--font-sans)',
      padding: 0,
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement(DWIcon, {
    name: "arrow-left",
    size: 16
  }), " Voltar para a lista"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "aegis-mono",
    style: {
      fontSize: 'var(--text-lg)',
      fontWeight: 700,
      color: 'var(--text-strong)'
    }
  }, r.id), /*#__PURE__*/React.createElement(DWBadge, {
    tone: r.tipo === 'Alarme' ? 'alert' : 'brand',
    dot: true
  }, r.tipo), /*#__PURE__*/React.createElement(DWBadge, {
    tone: SEV_TONE[r.sev],
    dot: true,
    size: "sm"
  }, r.sev), /*#__PURE__*/React.createElement(DWBadge, {
    tone: STATUS_TONE[r.status],
    size: "sm"
  }, r.status)), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 'var(--text-base)',
      color: 'var(--text-body)',
      lineHeight: 1.6,
      marginBottom: 20
    }
  }, r.desc), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: '14px 20px'
    }
  }, fields.map(([k, v]) => /*#__PURE__*/React.createElement("div", {
    key: k,
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 2
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "aegis-eyebrow"
  }, k), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-strong)',
      fontWeight: 500
    }
  }, v)))));
}
function Drawer({
  open,
  data,
  onClose,
  onClear
}) {
  const [loading, setLoading] = React.useState(false);
  const [expanded, setExpanded] = React.useState(null);
  const [detail, setDetail] = React.useState(null);
  React.useEffect(() => {
    if (open && data) {
      setLoading(true);
      setExpanded(null);
      setDetail(null);
      const t = setTimeout(() => setLoading(false), 520);
      return () => clearTimeout(t);
    }
  }, [open, data]);
  React.useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape' && open) onClose();
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  React.useEffect(() => {
    if (window.lucide) window.lucide.createIcons();
  });
  const d = data || {
    title: '',
    total: 0,
    chips: [],
    items: []
  };
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    onClick: onClose,
    style: {
      position: 'fixed',
      inset: 0,
      zIndex: 8000,
      background: 'var(--scrim)',
      opacity: open ? 1 : 0,
      pointerEvents: open ? 'auto' : 'none',
      transition: 'opacity var(--duration-base) var(--ease-standard)',
      backdropFilter: 'blur(1.5px)'
    }
  }), /*#__PURE__*/React.createElement("aside", {
    role: "dialog",
    "aria-modal": "true",
    style: {
      position: 'fixed',
      top: 0,
      right: 0,
      bottom: 0,
      zIndex: 8001,
      width: 'min(680px, max(360px, 52vw))',
      maxWidth: '100vw',
      background: 'var(--surface-raised)',
      boxShadow: 'var(--shadow-xl)',
      display: 'flex',
      flexDirection: 'column',
      transform: open ? 'translateX(0)' : 'translateX(101%)',
      transition: 'transform var(--duration-slow) var(--ease-out)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 'none',
      borderBottom: '1px solid var(--border-subtle)',
      background: 'var(--surface-card)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'flex-start',
      justifyContent: 'space-between',
      gap: 12,
      padding: '18px 22px 14px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("h2", {
    style: {
      fontSize: 'var(--text-xl)',
      fontWeight: 800,
      color: 'var(--text-strong)',
      lineHeight: 1.2
    }
  }, d.title), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-muted)',
      marginTop: 3
    }
  }, loading ? 'Carregando ocorrências…' : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("b", {
    className: "aegis-tnum",
    style: {
      color: 'var(--text-body)'
    }
  }, d.total), " ocorr\xEAncias encontradas"))), /*#__PURE__*/React.createElement(DWIconButton, {
    icon: "x",
    label: "Fechar",
    variant: "soft",
    onClick: onClose
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 12,
      padding: '0 22px 14px',
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      flexWrap: 'wrap'
    }
  }, d.chips.map((c, i) => /*#__PURE__*/React.createElement("span", {
    key: i,
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      height: 26,
      padding: '0 10px',
      borderRadius: 'var(--radius-pill)',
      background: 'var(--brand-soft)',
      color: 'var(--brand-strong)',
      fontSize: 'var(--text-xs)',
      fontWeight: 600
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-faint)',
      fontWeight: 500
    }
  }, c.label, ":"), " ", c.value))), /*#__PURE__*/React.createElement(DWButton, {
    variant: "ghost",
    size: "sm",
    icon: "eraser",
    onClick: onClear
  }, "Limpar filtro"))), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      overflowY: 'auto'
    }
  }, detail ? /*#__PURE__*/React.createElement(DrawerDetail, {
    r: detail,
    onBack: () => setDetail(null)
  }) : loading ? /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '8px 22px'
    }
  }, Array.from({
    length: 6
  }).map((_, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: 'flex',
      gap: 14,
      alignItems: 'center',
      padding: '14px 0',
      borderBottom: '1px solid var(--border-subtle)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 90
    }
  }, /*#__PURE__*/React.createElement(Skeleton, {
    w: "80%"
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement(Skeleton, {
    w: "60%"
  })), /*#__PURE__*/React.createElement(Skeleton, {
    w: 70,
    h: 20
  }), /*#__PURE__*/React.createElement(Skeleton, {
    w: 56,
    h: 20
  })))) : d.total === 0 ? /*#__PURE__*/React.createElement(DrawerEmpty, {
    onClear: onClear
  }) : /*#__PURE__*/React.createElement("table", {
    style: {
      width: '100%',
      borderCollapse: 'collapse'
    }
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", {
    style: {
      background: 'var(--surface-muted)',
      position: 'sticky',
      top: 0,
      zIndex: 1
    }
  }, ['Alerta', 'Local', 'Descrição', 'Severidade', 'Status', ''].map((c, i) => /*#__PURE__*/React.createElement("th", {
    key: i,
    style: {
      textAlign: 'left',
      padding: '10px 14px',
      fontSize: 'var(--text-2xs)',
      fontWeight: 700,
      letterSpacing: '0.06em',
      textTransform: 'uppercase',
      color: 'var(--text-muted)',
      whiteSpace: 'nowrap'
    }
  }, c)))), /*#__PURE__*/React.createElement("tbody", null, d.items.map((r, i) => /*#__PURE__*/React.createElement(React.Fragment, {
    key: r.id + i
  }, /*#__PURE__*/React.createElement("tr", {
    style: {
      borderBottom: '1px solid var(--border-subtle)'
    },
    onMouseEnter: e => e.currentTarget.style.background = 'var(--surface-muted)',
    onMouseLeave: e => e.currentTarget.style.background = 'transparent'
  }, /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '12px 14px',
      verticalAlign: 'top'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'flex-start',
      gap: 7
    }
  }, /*#__PURE__*/React.createElement("button", {
    onClick: () => setExpanded(expanded === i ? null : i),
    title: "Detalhes r\xE1pidos",
    style: {
      border: 'none',
      background: 'transparent',
      cursor: 'pointer',
      color: 'var(--text-faint)',
      padding: 0,
      marginTop: 1,
      display: 'inline-flex'
    }
  }, /*#__PURE__*/React.createElement(DWIcon, {
    name: expanded === i ? 'chevron-down' : 'chevron-right',
    size: 15
  })), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "aegis-mono",
    style: {
      fontSize: 'var(--text-2xs)',
      color: 'var(--text-muted)',
      marginBottom: 4
    }
  }, r.id), /*#__PURE__*/React.createElement(DWBadge, {
    tone: r.tipo === 'Alarme' ? 'alert' : 'brand',
    size: "sm",
    dot: true
  }, r.tipo)))), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '12px 14px',
      verticalAlign: 'top',
      maxWidth: 150
    }
  }, /*#__PURE__*/React.createElement("span", {
    title: r.local,
    style: {
      display: 'block',
      fontSize: 'var(--text-xs)',
      color: 'var(--text-strong)',
      fontWeight: 500,
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap'
    }
  }, r.local)), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '12px 14px',
      verticalAlign: 'top',
      maxWidth: 200
    }
  }, /*#__PURE__*/React.createElement("span", {
    title: r.desc,
    style: {
      display: 'block',
      fontSize: 'var(--text-xs)',
      color: 'var(--text-body)',
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap'
    }
  }, r.desc)), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '12px 14px',
      verticalAlign: 'top'
    }
  }, /*#__PURE__*/React.createElement(DWBadge, {
    tone: SEV_TONE[r.sev],
    dot: true,
    size: "sm"
  }, r.sev)), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '12px 14px',
      verticalAlign: 'top'
    }
  }, /*#__PURE__*/React.createElement(DWBadge, {
    tone: STATUS_TONE[r.status],
    size: "sm"
  }, r.status)), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '12px 14px',
      verticalAlign: 'top',
      whiteSpace: 'nowrap'
    }
  }, /*#__PURE__*/React.createElement(DWButton, {
    variant: "ghost",
    size: "sm",
    icon: "search",
    onClick: () => setDetail(r)
  }, "Inspecionar"))), expanded === i && /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("td", {
    colSpan: 6,
    style: {
      padding: '0 14px 12px'
    }
  }, /*#__PURE__*/React.createElement(RowDetail, {
    r: r
  }))))))))));
}
Object.assign(window, {
  Drawer
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/visao-executiva/Drawer.jsx", error: String((e && e.message) || e) }); }

// ui_kits/visao-executiva/FilterBar.jsx
try { (() => {
/* Visão Executiva — filter bar card */
const {
  Icon: FBIcon,
  Select: FBSelect,
  DateField: FBDate,
  Button: FBButton,
  Badge: FBBadge
} = window.AegisDesignSystem_86ea41;
function FilterBar({
  data
}) {
  const [expanded, setExpanded] = React.useState(true);
  const [client, setClient] = React.useState('acme');
  const [site, setSite] = React.useState('all');
  const [system, setSystem] = React.useState('all');
  const [d1, setD1] = React.useState('2024-06-01');
  const [d2, setD2] = React.useState('2024-06-25');
  const [d3, setD3] = React.useState('');
  const [d4, setD4] = React.useState('');
  const toOpts = arr => arr.map(x => ({
    label: x,
    value: x.toLowerCase()
  }));
  return /*#__PURE__*/React.createElement("div", {
    style: {
      background: 'var(--surface-card)',
      border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-xl)',
      boxShadow: 'var(--shadow-sm)',
      padding: 'var(--space-5)',
      display: 'flex',
      flexDirection: 'column',
      gap: 18
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'flex-end',
      gap: 12,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 9,
      height: 'var(--control-h-md)',
      paddingRight: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 34,
      height: 34,
      borderRadius: 'var(--radius-md)',
      background: 'var(--brand-soft)',
      color: 'var(--brand-strong)'
    }
  }, /*#__PURE__*/React.createElement(FBIcon, {
    name: "sliders-horizontal",
    size: 17
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-base)',
      fontWeight: 700,
      color: 'var(--text-strong)'
    }
  }, "Filtros")), /*#__PURE__*/React.createElement(FBSelect, {
    label: "Cliente",
    value: client,
    onChange: setClient,
    options: data.clients,
    wrapStyle: {
      width: 190
    },
    icon: /*#__PURE__*/React.createElement(FBIcon, {
      name: "building-2",
      size: 15
    })
  }), /*#__PURE__*/React.createElement(FBSelect, {
    label: "Site / Unidade",
    value: site,
    onChange: setSite,
    options: data.sites,
    wrapStyle: {
      width: 180
    }
  }), /*#__PURE__*/React.createElement(FBSelect, {
    label: "Sistema",
    value: system,
    onChange: setSystem,
    options: data.systems,
    wrapStyle: {
      width: 170
    }
  }), /*#__PURE__*/React.createElement(FBButton, {
    variant: "secondary",
    icon: "plus",
    iconRight: expanded ? 'chevron-up' : 'chevron-down',
    onClick: () => setExpanded(e => !e)
  }, "Mais filtros"), /*#__PURE__*/React.createElement(FBBadge, {
    tone: "brand",
    dot: true
  }, "4 ativos"), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-muted)',
      fontWeight: 500
    }
  }, /*#__PURE__*/React.createElement("b", {
    className: "aegis-tnum",
    style: {
      color: 'var(--text-strong)'
    }
  }, "170"), " registros"), /*#__PURE__*/React.createElement(FBButton, {
    variant: "ghost",
    icon: "eraser"
  }, "Limpar"), /*#__PURE__*/React.createElement(FBButton, {
    variant: "primary",
    icon: "check"
  }, "Aplicar")), expanded && /*#__PURE__*/React.createElement("div", {
    style: {
      height: 1,
      background: 'var(--border-subtle)'
    }
  }), expanded && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(4, 1fr)',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement(FBDate, {
    label: "Abertura \u2014 de",
    value: d1,
    onChange: setD1
  }), /*#__PURE__*/React.createElement(FBDate, {
    label: "Abertura \u2014 at\xE9",
    value: d2,
    onChange: setD2
  }), /*#__PURE__*/React.createElement(FBDate, {
    label: "Fechamento \u2014 de",
    value: d3,
    onChange: setD3
  }), /*#__PURE__*/React.createElement(FBDate, {
    label: "Fechamento \u2014 at\xE9",
    value: d4,
    onChange: setD4
  })), expanded && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(5, 1fr)',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement(FBSelect, {
    label: "Categoria",
    options: toOpts(data.categories),
    value: "todas"
  }), /*#__PURE__*/React.createElement(FBSelect, {
    label: "\xC1rea / Ambiente",
    options: toOpts(data.areas),
    value: "todas"
  }), /*#__PURE__*/React.createElement(FBSelect, {
    label: "Tipo de Equipamento",
    options: toOpts(data.equipTypes),
    value: "todos"
  }), /*#__PURE__*/React.createElement(FBSelect, {
    label: "Tipo de Alerta",
    options: toOpts(data.alertTypes),
    value: "todos"
  }), /*#__PURE__*/React.createElement(FBSelect, {
    label: "Status",
    options: toOpts(data.statuses),
    value: "todos"
  })));
}
Object.assign(window, {
  FilterBar
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/visao-executiva/FilterBar.jsx", error: String((e && e.message) || e) }); }

// ui_kits/visao-executiva/Header.jsx
try { (() => {
/* Visão Executiva — top header */
const {
  Icon: HDIcon,
  IconButton: HDIconButton,
  Avatar: HDAvatar,
  Switch: HDSwitch
} = window.AegisDesignSystem_86ea41;
function Header({
  dark,
  onToggleTheme,
  user,
  tenant
}) {
  return /*#__PURE__*/React.createElement("header", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 20,
      padding: '20px 28px',
      minHeight: 'var(--header-height)',
      flex: 'none',
      background: 'var(--surface-card)',
      borderBottom: '1px solid var(--border-subtle)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 14,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 44,
      height: 44,
      flex: 'none',
      borderRadius: 'var(--radius-lg)',
      background: 'var(--brand-soft)',
      color: 'var(--brand-strong)'
    }
  }, /*#__PURE__*/React.createElement(HDIcon, {
    name: "layout-dashboard",
    size: 22
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      fontSize: 'var(--text-2xl)',
      fontWeight: 800,
      color: 'var(--text-strong)',
      lineHeight: 1.1
    }
  }, "Vis\xE3o Executiva"), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-muted)',
      marginTop: 2
    }
  }, "Resumo gerencial das opera\xE7\xF5es e indicadores principais"))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 7,
      padding: '6px 12px 6px 6px',
      background: 'var(--surface-muted)',
      borderRadius: 'var(--radius-pill)',
      marginRight: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 26,
      height: 26,
      borderRadius: '50%',
      background: 'var(--brand)',
      color: '#fff',
      fontSize: 11,
      fontWeight: 700
    }
  }, tenant.name[0]), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-xs)',
      fontWeight: 600,
      color: 'var(--text-body)'
    }
  }, tenant.name), /*#__PURE__*/React.createElement(HDIcon, {
    name: "chevrons-up-down",
    size: 14,
    color: "var(--text-faint)"
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 7,
      padding: '0 8px',
      borderRight: '1px solid var(--border-subtle)',
      marginRight: 4
    }
  }, /*#__PURE__*/React.createElement(HDIcon, {
    name: dark ? 'moon' : 'sun',
    size: 16,
    color: "var(--text-faint)"
  }), /*#__PURE__*/React.createElement(HDSwitch, {
    checked: dark,
    onChange: onToggleTheme,
    size: "sm"
  })), /*#__PURE__*/React.createElement(HDIconButton, {
    icon: "search",
    label: "Buscar"
  }), /*#__PURE__*/React.createElement(HDIconButton, {
    icon: "mail",
    label: "Mensagens",
    badge: 2
  }), /*#__PURE__*/React.createElement(HDIconButton, {
    icon: "bell",
    label: "Notifica\xE7\xF5es",
    badge: 5
  }), /*#__PURE__*/React.createElement(HDAvatar, {
    name: user.name,
    size: "md",
    status: "online",
    style: {
      marginLeft: 4
    }
  })));
}
Object.assign(window, {
  Header
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/visao-executiva/Header.jsx", error: String((e && e.message) || e) }); }

// ui_kits/visao-executiva/OccurrencesTable.jsx
try { (() => {
/* Visão Executiva — occurrences data table */
const {
  Icon: TBIcon,
  Badge: TBBadge,
  Button: TBButton,
  IconButton: TBIconButton,
  SegmentedControl: TBSeg,
  Select: TBSelect
} = window.AegisDesignSystem_86ea41;
const sevTone = {
  'Crítica': 'bad',
  'Alta': 'alert',
  'Normal': 'good'
};
const statusTone = {
  'Aberto': 'bad',
  'Em análise': 'alert',
  'Resolvido': 'good'
};
function OccurrencesTable({
  rows
}) {
  const [view, setView] = React.useState('Todos');
  const [menuRow, setMenuRow] = React.useState(null);
  const filtered = rows.filter(r => view === 'Todos' ? true : view === 'Alarmes' ? r.type === 'Alarme' : r.type === 'Anomalia');
  const cols = ['Alerta', 'Local', 'Descrição', 'Severidade', 'Status', 'Abertura', 'Atualização', ''];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      background: 'var(--surface-card)',
      border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-xl)',
      boxShadow: 'var(--shadow-sm)',
      overflow: 'hidden',
      flex: 'none'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 16,
      padding: '18px 22px',
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 11
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 36,
      height: 36,
      borderRadius: 'var(--radius-lg)',
      background: 'var(--alert-background)',
      color: 'var(--alert-foreground)'
    }
  }, /*#__PURE__*/React.createElement(TBIcon, {
    name: "triangle-alert",
    size: 18
  })), /*#__PURE__*/React.createElement("h3", {
    style: {
      fontSize: 'var(--text-lg)',
      fontWeight: 700,
      color: 'var(--text-strong)'
    }
  }, "Ocorr\xEAncias"), /*#__PURE__*/React.createElement(TBBadge, {
    tone: "brand"
  }, "85 ocorr\xEAncias")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement(TBSeg, {
    options: ['Todos', 'Alarmes', 'Anomalias'],
    value: view,
    onChange: setView,
    size: "sm"
  }), /*#__PURE__*/React.createElement(TBSelect, {
    options: [{
      label: 'Agrupar por Local',
      value: 'local'
    }, {
      label: 'Agrupar por Sistema',
      value: 'sys'
    }],
    value: "local",
    shape: "pill",
    size: "sm",
    fullWidth: false,
    wrapStyle: {
      width: 190
    }
  }), /*#__PURE__*/React.createElement(TBButton, {
    variant: "secondary",
    size: "sm",
    icon: "download"
  }, "Baixar XLS"))), /*#__PURE__*/React.createElement("div", {
    style: {
      overflowX: 'auto'
    }
  }, /*#__PURE__*/React.createElement("table", {
    style: {
      width: '100%',
      borderCollapse: 'collapse',
      minWidth: 920
    }
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", {
    style: {
      background: 'var(--surface-muted)'
    }
  }, cols.map((c, i) => /*#__PURE__*/React.createElement("th", {
    key: i,
    style: {
      textAlign: 'left',
      padding: '11px 16px',
      fontSize: 'var(--text-2xs)',
      fontWeight: 700,
      letterSpacing: '0.06em',
      textTransform: 'uppercase',
      color: 'var(--text-muted)',
      whiteSpace: 'nowrap'
    }
  }, c)))), /*#__PURE__*/React.createElement("tbody", null, filtered.map((r, i) => /*#__PURE__*/React.createElement("tr", {
    key: r.code,
    onMouseEnter: e => e.currentTarget.style.background = 'var(--surface-muted)',
    onMouseLeave: e => e.currentTarget.style.background = 'transparent',
    style: {
      borderTop: '1px solid var(--border-subtle)',
      transition: 'background var(--duration-fast)'
    }
  }, /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '13px 16px',
      whiteSpace: 'nowrap'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 7,
      height: 7,
      borderRadius: '50%',
      flex: 'none',
      background: r.type === 'Alarme' ? 'var(--categorical-7)' : 'var(--categorical-6)'
    }
  }), /*#__PURE__*/React.createElement("span", {
    className: "aegis-mono",
    style: {
      fontSize: 'var(--text-xs)',
      fontWeight: 600,
      color: 'var(--text-strong)'
    }
  }, r.code))), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '13px 16px',
      whiteSpace: 'nowrap'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-sm)',
      fontWeight: 600,
      color: 'var(--text-strong)'
    }
  }, r.site), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-2xs)',
      color: 'var(--text-faint)'
    }
  }, r.area)), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '13px 16px',
      maxWidth: 280
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-sm)',
      color: 'var(--text-body)'
    }
  }, r.desc)), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '13px 16px'
    }
  }, /*#__PURE__*/React.createElement(TBBadge, {
    tone: sevTone[r.sev],
    dot: true,
    size: "sm"
  }, r.sev)), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '13px 16px'
    }
  }, /*#__PURE__*/React.createElement(TBBadge, {
    tone: statusTone[r.status],
    size: "sm"
  }, r.status)), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '13px 16px',
      whiteSpace: 'nowrap'
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "aegis-mono",
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)'
    }
  }, r.open)), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '13px 16px',
      whiteSpace: 'nowrap'
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "aegis-mono",
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)'
    }
  }, r.upd)), /*#__PURE__*/React.createElement("td", {
    style: {
      padding: '13px 16px',
      position: 'relative'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 4
    }
  }, /*#__PURE__*/React.createElement(TBIconButton, {
    icon: "eye",
    label: "Visualizar",
    variant: "ghost",
    size: "sm"
  }), /*#__PURE__*/React.createElement(TBIconButton, {
    icon: "more-vertical",
    label: "Mais",
    variant: "ghost",
    size: "sm",
    onClick: () => setMenuRow(menuRow === i ? null : i)
  })), menuRow === i && /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      top: 44,
      right: 12,
      zIndex: 30,
      minWidth: 168,
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--radius-md)',
      boxShadow: 'var(--shadow-lg)',
      padding: 5
    }
  }, [['external-link', 'Abrir detalhe'], ['user-plus', 'Atribuir'], ['check-check', 'Resolver'], ['bell-off', 'Silenciar']].map(([ic, lb]) => /*#__PURE__*/React.createElement("button", {
    key: lb,
    onClick: () => setMenuRow(null),
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 9,
      width: '100%',
      padding: '8px 10px',
      border: 'none',
      background: 'transparent',
      cursor: 'pointer',
      borderRadius: 'var(--radius-sm)',
      fontSize: 'var(--text-sm)',
      color: 'var(--text-body)',
      fontFamily: 'var(--font-sans)'
    },
    onMouseEnter: e => e.currentTarget.style.background = 'var(--surface-muted)',
    onMouseLeave: e => e.currentTarget.style.background = 'transparent'
  }, /*#__PURE__*/React.createElement(TBIcon, {
    name: ic,
    size: 15
  }), " ", lb))))))))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 16,
      padding: '14px 22px',
      borderTop: '1px solid var(--border-subtle)',
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-xs)',
      color: 'var(--text-muted)'
    }
  }, "Mostrando ", /*#__PURE__*/React.createElement("b", {
    style: {
      color: 'var(--text-strong)'
    }
  }, "1\u2013", filtered.length), " de 85 ocorr\xEAncias"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 6
    }
  }, /*#__PURE__*/React.createElement(TBIconButton, {
    icon: "chevron-left",
    label: "Anterior",
    variant: "soft",
    size: "sm"
  }), ['1', '2', '3'].map(p => /*#__PURE__*/React.createElement("button", {
    key: p,
    style: {
      width: 32,
      height: 32,
      borderRadius: 'var(--radius-md)',
      border: p === '1' ? '1px solid transparent' : '1px solid var(--control-border)',
      background: p === '1' ? 'var(--brand)' : 'var(--control-bg)',
      color: p === '1' ? '#fff' : 'var(--text-body)',
      fontSize: 'var(--text-sm)',
      fontWeight: 600,
      cursor: 'pointer',
      fontFamily: 'var(--font-sans)'
    }
  }, p)), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-faint)',
      padding: '0 2px'
    }
  }, "\u2026"), /*#__PURE__*/React.createElement("button", {
    style: {
      width: 32,
      height: 32,
      borderRadius: 'var(--radius-md)',
      border: '1px solid var(--control-border)',
      background: 'var(--control-bg)',
      color: 'var(--text-body)',
      fontSize: 'var(--text-sm)',
      fontWeight: 600,
      cursor: 'pointer',
      fontFamily: 'var(--font-sans)'
    }
  }, "11"), /*#__PURE__*/React.createElement(TBIconButton, {
    icon: "chevron-right",
    label: "Pr\xF3ximo",
    variant: "soft",
    size: "sm"
  }))));
}
Object.assign(window, {
  OccurrencesTable
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/visao-executiva/OccurrencesTable.jsx", error: String((e && e.message) || e) }); }

// ui_kits/visao-executiva/Sidebar.jsx
try { (() => {
/* Visão Executiva — fixed sidebar */
const {
  Icon: SBIcon,
  Avatar: SBAvatar
} = window.AegisDesignSystem_86ea41;
const NAV = [{
  id: 'exec',
  label: 'Visão Executiva',
  icon: 'layout-dashboard'
}, {
  id: 'ops',
  label: 'Visão Operacional',
  icon: 'activity'
}, {
  id: 'health',
  label: 'Saúde dos Equipamentos',
  icon: 'heart-pulse'
}, {
  id: 'reports',
  label: 'Relatórios',
  icon: 'file-bar-chart-2'
}, {
  id: 'admin',
  label: 'Admin',
  icon: 'shield'
}];
function SidebarItem({
  item,
  active,
  collapsed,
  onClick
}) {
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("button", {
    onClick: onClick,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    title: collapsed ? item.label : undefined,
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      width: '100%',
      padding: collapsed ? '11px' : '11px 14px',
      justifyContent: collapsed ? 'center' : 'flex-start',
      border: 'none',
      cursor: 'pointer',
      borderRadius: 'var(--radius-md)',
      background: active ? 'var(--brand)' : hover ? 'rgba(255,255,255,0.07)' : 'transparent',
      color: active ? '#fff' : hover ? '#fff' : 'rgba(231,237,245,0.72)',
      fontFamily: 'var(--font-sans)',
      fontSize: 'var(--text-sm)',
      fontWeight: active ? 700 : 500,
      boxShadow: active ? '0 6px 16px rgba(1,93,252,0.35)' : 'none',
      transition: 'var(--transition-control)',
      textAlign: 'left',
      whiteSpace: 'nowrap'
    }
  }, /*#__PURE__*/React.createElement(SBIcon, {
    name: item.icon,
    size: 19,
    strokeWidth: active ? 2.2 : 1.9
  }), !collapsed && /*#__PURE__*/React.createElement("span", {
    style: {
      overflow: 'hidden',
      textOverflow: 'ellipsis'
    }
  }, item.label));
}
function Sidebar({
  active,
  onNavigate,
  collapsed,
  onToggle,
  user
}) {
  return /*#__PURE__*/React.createElement("aside", {
    style: {
      width: collapsed ? 'var(--sidebar-width-collapsed)' : 'var(--sidebar-width)',
      flex: 'none',
      background: 'var(--surface-sidebar)',
      height: '100%',
      overflowY: 'auto',
      display: 'flex',
      flexDirection: 'column',
      padding: collapsed ? '20px 12px' : '22px 18px',
      transition: 'width var(--duration-slow) var(--ease-out)',
      position: 'relative'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 11,
      padding: collapsed ? 0 : '0 6px',
      justifyContent: collapsed ? 'center' : 'flex-start',
      marginBottom: 26,
      height: 40
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: window.__resources && window.__resources.aegisLogo || "../../assets/aegis-symbol-white.png",
    alt: "Aegis",
    style: {
      height: 30,
      flex: 'none'
    }
  }), !collapsed && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 21,
      fontWeight: 800,
      letterSpacing: '-0.5px',
      color: '#F5F7FA'
    }
  }, "Aegis")), /*#__PURE__*/React.createElement("nav", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 4,
      flex: 1
    }
  }, !collapsed && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--text-2xs)',
      fontWeight: 700,
      letterSpacing: '0.08em',
      textTransform: 'uppercase',
      color: 'rgba(231,237,245,0.4)',
      padding: '0 14px',
      marginBottom: 6
    }
  }, "Monitoramento"), NAV.map(n => /*#__PURE__*/React.createElement(SidebarItem, {
    key: n.id,
    item: n,
    active: active === n.id,
    collapsed: collapsed,
    onClick: () => onNavigate(n.id)
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 1,
      background: 'rgba(255,255,255,0.08)',
      margin: '14px 8px'
    }
  }), /*#__PURE__*/React.createElement(SidebarItem, {
    item: {
      id: 'help',
      label: 'Central de Ajuda',
      icon: 'life-buoy'
    },
    collapsed: collapsed,
    active: false,
    onClick: () => {}
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 16,
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      padding: collapsed ? 8 : 10,
      borderRadius: 'var(--radius-lg)',
      background: 'rgba(255,255,255,0.05)',
      border: '1px solid rgba(255,255,255,0.08)',
      justifyContent: collapsed ? 'center' : 'flex-start',
      cursor: 'pointer'
    }
  }, /*#__PURE__*/React.createElement(SBAvatar, {
    name: user.name,
    size: "sm",
    status: "online"
  }), !collapsed && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 'var(--text-xs)',
      fontWeight: 600,
      color: '#F5F7FA',
      whiteSpace: 'nowrap',
      overflow: 'hidden',
      textOverflow: 'ellipsis'
    }
  }, user.email), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      marginTop: 3,
      fontSize: 9,
      fontWeight: 700,
      letterSpacing: '0.04em',
      textTransform: 'uppercase',
      color: 'var(--categorical-2)',
      background: 'rgba(255,140,0,0.18)',
      padding: '1px 7px',
      borderRadius: 'var(--radius-pill)'
    }
  }, user.role)), /*#__PURE__*/React.createElement(SBIcon, {
    name: "chevron-up",
    size: 16,
    color: "rgba(231,237,245,0.6)"
  }))), /*#__PURE__*/React.createElement("button", {
    onClick: onToggle,
    title: collapsed ? 'Expandir' : 'Recolher',
    style: {
      position: 'absolute',
      top: 30,
      right: -13,
      width: 26,
      height: 26,
      borderRadius: '50%',
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)',
      color: 'var(--text-muted)',
      cursor: 'pointer',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      boxShadow: 'var(--shadow-sm)',
      zIndex: 5
    }
  }, /*#__PURE__*/React.createElement(SBIcon, {
    name: collapsed ? 'chevron-right' : 'chevron-left',
    size: 15
  })));
}
Object.assign(window, {
  Sidebar
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/visao-executiva/Sidebar.jsx", error: String((e && e.message) || e) }); }

// ui_kits/visao-executiva/data.js
try { (() => {
/* Sample (mock) data for the Visão Executiva UI kit.
   In production these arrive from Supabase, filtered by tenant_id. */
window.AEGIS_DATA = {
  tenant: {
    id: 'acme',
    name: 'ACME Energia'
  },
  user: {
    name: 'Rodrigo Andrade',
    email: 'rodrigo@acme.com.br',
    role: 'Admin'
  },
  clients: [{
    label: 'ACME Energia',
    value: 'acme'
  }, {
    label: 'Vortex Telecom',
    value: 'vortex'
  }, {
    label: 'Hydra Logística',
    value: 'hydra'
  }],
  sites: [{
    label: 'Todas as unidades',
    value: 'all'
  }, {
    label: 'SP Tower',
    value: 'sp'
  }, {
    label: 'RJ Data Center',
    value: 'rj'
  }, {
    label: 'MG Planta 1',
    value: 'mg'
  }, {
    label: 'BA Unidade',
    value: 'ba'
  }],
  systems: [{
    label: 'Todos os sistemas',
    value: 'all'
  }, {
    label: 'Refrigeração',
    value: 'cool'
  }, {
    label: 'Energia',
    value: 'power'
  }, {
    label: 'Rede',
    value: 'net'
  }],
  categories: ['Todas', 'Térmico', 'Elétrico', 'Mecânico', 'Rede', 'Segurança'],
  areas: ['Todas', 'Sala de Racks', 'Subestação', 'Casa de Máquinas', 'Pátio'],
  equipTypes: ['Todos', 'Chiller', 'Compressor', 'UPS', 'Switch', 'Gerador'],
  alertTypes: ['Todos', 'Alarme', 'Anomalia', 'Manutenção'],
  statuses: ['Todos', 'Aberto', 'Em análise', 'Resolvido'],
  kpis: {
    total: 85,
    alarms: 12,
    anomalies: 7,
    critical: 4,
    expAnomalies: '156h',
    expAlarms: '23h'
  },
  bySite: [{
    name: 'SP Tower',
    value: 62,
    dist: {
      critico: 4,
      moderado: 33,
      leve: 25
    }
  }, {
    name: 'RJ Data Center',
    value: 14,
    dist: {
      critico: 2,
      moderado: 7,
      leve: 5
    }
  }, {
    name: 'MG Planta 1',
    value: 8,
    dist: {
      critico: 0,
      moderado: 5,
      leve: 3
    }
  }, {
    name: 'BA Unidade',
    value: 1,
    dist: {
      critico: 0,
      moderado: 1,
      leve: 0
    }
  }],
  pareto: [{
    name: 'Térmico',
    value: 28,
    dist: {
      critico: 2,
      moderado: 16,
      leve: 10
    }
  }, {
    name: 'Elétrico',
    value: 19,
    dist: {
      critico: 1,
      moderado: 11,
      leve: 7
    }
  }, {
    name: 'Mecânico',
    value: 14,
    dist: {
      critico: 1,
      moderado: 8,
      leve: 5
    }
  }, {
    name: 'Rede',
    value: 10,
    dist: {
      critico: 0,
      moderado: 6,
      leve: 4
    }
  }, {
    name: 'Segurança',
    value: 7,
    dist: {
      critico: 0,
      moderado: 3,
      leve: 4
    }
  }, {
    name: 'Fluidos',
    value: 4,
    dist: {
      critico: 0,
      moderado: 2,
      leve: 2
    }
  }, {
    name: 'Sensor',
    value: 2,
    dist: {
      critico: 0,
      moderado: 1,
      leve: 1
    }
  }, {
    name: 'Produção',
    value: 1,
    dist: {
      critico: 0,
      moderado: 0,
      leve: 1
    }
  }],
  trend: [{
    d: '01/06',
    v: 41,
    nova: 3
  }, {
    d: '04/06',
    v: 46,
    nova: 6
  }, {
    d: '07/06',
    v: 52,
    nova: 7
  }, {
    d: '10/06',
    v: 49,
    nova: 2
  }, {
    d: '13/06',
    v: 58,
    nova: 11
  }, {
    d: '16/06',
    v: 63,
    nova: 8
  }, {
    d: '19/06',
    v: 60,
    nova: 4
  }, {
    d: '22/06',
    v: 71,
    nova: 13
  }, {
    d: '25/06',
    v: 78,
    nova: 9
  }, {
    d: '28/06',
    v: 85,
    nova: 10
  }],
  treemap: [{
    name: 'Conjunto 12',
    value: 32,
    site: 'SP Tower',
    ambiente: 'CONJUNTO 12',
    dist: {
      critico: 3,
      moderado: 18,
      leve: 11
    }
  }, {
    name: 'Conjunto 132',
    value: 19,
    site: 'RJ Data Center',
    ambiente: 'CONJUNTO 132',
    dist: {
      critico: 2,
      moderado: 11,
      leve: 6
    }
  }, {
    name: 'Conjunto 21',
    value: 12,
    site: 'SP Tower',
    ambiente: 'CONJUNTO 21',
    dist: {
      critico: 1,
      moderado: 7,
      leve: 4
    }
  }, {
    name: 'Conjunto 42',
    value: 9,
    site: 'SP Tower',
    ambiente: 'CONJUNTO 42',
    dist: {
      critico: 0,
      moderado: 6,
      leve: 3
    }
  }, {
    name: 'Conjunto 02',
    value: 7,
    site: 'MG Planta 1',
    ambiente: 'CONJUNTO 02',
    dist: {
      critico: 0,
      moderado: 4,
      leve: 3
    }
  }, {
    name: 'Conjunto 01',
    value: 5,
    site: 'RJ Data Center',
    ambiente: 'CONJUNTO 01',
    dist: {
      critico: 0,
      moderado: 3,
      leve: 2
    }
  }, {
    name: 'Conjunto 08',
    value: 2,
    site: 'BA Unidade',
    ambiente: 'CONJUNTO 08',
    dist: {
      critico: 0,
      moderado: 1,
      leve: 1
    }
  }],
  occurrences: [{
    code: 'ALM-2024-00085',
    type: 'Alarme',
    site: 'SP Tower',
    area: 'Sala 12',
    desc: 'Temperatura acima do limite no rack principal',
    sev: 'Crítica',
    status: 'Aberto',
    open: '25/06/2024 09:21',
    upd: '25/06/2024 10:15'
  }, {
    code: 'ANM-2024-00084',
    type: 'Anomalia',
    site: 'RJ Data Center',
    area: 'Sala 03',
    desc: 'Vibração acima do normal no compressor #2',
    sev: 'Alta',
    status: 'Aberto',
    open: '25/06/2024 08:47',
    upd: '25/06/2024 09:50'
  }, {
    code: 'ALM-2024-00083',
    type: 'Alarme',
    site: 'SP Tower',
    area: 'Subestação',
    desc: 'Tensão fora da faixa na fase B',
    sev: 'Alta',
    status: 'Em análise',
    open: '24/06/2024 22:10',
    upd: '25/06/2024 07:02'
  }, {
    code: 'ANM-2024-00082',
    type: 'Anomalia',
    site: 'MG Planta 1',
    area: 'Casa de Máquinas',
    desc: 'Consumo de energia 18% acima da linha base',
    sev: 'Normal',
    status: 'Aberto',
    open: '24/06/2024 18:33',
    upd: '24/06/2024 20:41'
  }, {
    code: 'ALM-2024-00081',
    type: 'Alarme',
    site: 'SP Tower',
    area: 'Sala 12',
    desc: 'Umidade relativa abaixo do mínimo recomendado',
    sev: 'Normal',
    status: 'Resolvido',
    open: '24/06/2024 14:05',
    upd: '24/06/2024 16:20'
  }, {
    code: 'ANM-2024-00080',
    type: 'Anomalia',
    site: 'BA Unidade',
    area: 'Pátio',
    desc: 'Oscilação intermitente no gerador auxiliar',
    sev: 'Alta',
    status: 'Aberto',
    open: '24/06/2024 11:48',
    upd: '24/06/2024 13:12'
  }, {
    code: 'ALM-2024-00079',
    type: 'Alarme',
    site: 'RJ Data Center',
    area: 'Sala 03',
    desc: 'Falha de comunicação no switch de borda',
    sev: 'Crítica',
    status: 'Em análise',
    open: '23/06/2024 23:59',
    upd: '24/06/2024 06:30'
  }, {
    code: 'ALM-2024-00078',
    type: 'Alarme',
    site: 'MG Planta 1',
    area: 'Subestação',
    desc: 'Disjuntor principal operando próximo ao limite',
    sev: 'Normal',
    status: 'Resolvido',
    open: '23/06/2024 16:14',
    upd: '23/06/2024 19:05'
  }]
};

/* KPI tooltip copy (info on hover) */
window.AEGIS_DATA.kpiInfo = {
  total: 'Total de registros encontrados com os filtros aplicados. Inclui alarmes, anomalias e demais ocorrências do período.',
  alarms: 'Quantidade de alarmes em aberto no período filtrado. Considera apenas registros com status aberto.',
  anomalies: 'Quantidade de anomalias em aberto no período filtrado.',
  critical: 'Quantidade de ocorrências classificadas como críticas e ainda abertas.',
  expAnomalies: 'Tempo médio em que as anomalias permaneceram abertas no período selecionado.',
  expAlarms: 'Tempo médio em que os alarmes permaneceram abertos no período selecionado.'
};

/* ---- Drill-down generator (mock) ----
   In production this is a Supabase query scoped by tenant_id + global filters. */
(function () {
  const D = window.AEGIS_DATA;
  const DESCR = ['A leitura do sensor de temperatura do tubo de entrada está inconsistente com o histórico recente', 'Vibração acima do normal detectada no compressor durante o ciclo de carga', 'Tensão fora da faixa nominal na fase B do barramento principal', 'Consumo de energia acima da linha base projetada para o equipamento', 'Umidade relativa abaixo do mínimo recomendado para a sala técnica', 'Falha intermitente de comunicação no switch de borda do rack', 'Disjuntor principal operando próximo ao limite de corrente', 'Oscilação de rotação no gerador auxiliar sob carga parcial', 'Pressão diferencial elevada no filtro de ar do chiller', 'Atraso de resposta do PLC acima do limite configurado'];
  const SEV = ['Crítica', 'Alta', 'Moderada', 'Leve'];
  const STA = ['Aberto', 'Em tratamento', 'Resolvido'];
  const TIPOS = ['Alarme', 'Anomalia'];
  function rng(seed) {
    let s = seed || 1;
    return () => (s = s * 1103515245 + 12345 & 0x7fffffff) / 0x7fffffff;
  }
  function build(total, ctxSite, ctxAmb, seedStr) {
    let seed = 7;
    for (const c of seedStr || 'x') seed += c.charCodeAt(0);
    const r = rng(seed + total);
    const n = Math.min(total, 14);
    const items = [];
    for (let i = 0; i < n; i++) {
      const tipo = TIPOS[Math.floor(r() * TIPOS.length)];
      const site = ctxSite || D.bySite[Math.floor(r() * D.bySite.length)].name;
      const amb = ctxAmb || ['CONJUNTO 12', 'CONJUNTO 21', 'CONJUNTO 42', 'Sala 03', 'Subestação'][Math.floor(r() * 5)];
      const sev = i === 0 && total > 20 ? 'Moderada' : SEV[Math.floor(r() * SEV.length)];
      items.push({
        id: String(24910000 + Math.floor(r() * 89999)),
        tipo,
        local: `${site} • ${amb} • ${amb.toUpperCase()}`,
        site,
        ambiente: amb,
        desc: DESCR[Math.floor(r() * DESCR.length)],
        sev,
        status: STA[Math.floor(r() * STA.length)],
        equip: ['Chiller CH-02', 'Compressor CP-2', 'UPS-01', 'Switch SW-7', 'Gerador G-AUX'][Math.floor(r() * 5)],
        sistema: ['Refrigeração', 'Energia', 'Rede'][Math.floor(r() * 3)],
        open: `${10 + Math.floor(r() * 18)}/06/2024 ${String(Math.floor(r() * 24)).padStart(2, '0')}:${String(Math.floor(r() * 60)).padStart(2, '0')}`,
        upd: `${20 + Math.floor(r() * 8)}/06/2024 ${String(Math.floor(r() * 24)).padStart(2, '0')}:${String(Math.floor(r() * 60)).padStart(2, '0')}`
      });
    }
    return items;
  }
  D.drilldown = function (filterType, value, extra) {
    let total = 0,
      site = null,
      amb = null,
      chips = [],
      title = '';
    if (filterType === 'site') {
      const it = D.bySite.find(s => s.name === value) || {
        value: 0
      };
      total = it.value;
      site = value;
      title = `Ocorrências — ${value}`;
      chips = [{
        label: 'Site',
        value
      }];
    } else if (filterType === 'categoria') {
      const it = D.pareto.find(s => s.name === value) || {
        value: 0
      };
      total = it.value;
      title = `Ocorrências — ${value}`;
      chips = [{
        label: 'Categoria',
        value
      }];
    } else if (filterType === 'data') {
      const it = D.trend.find(s => s.d === value) || {
        v: 0
      };
      total = it.v;
      title = `Ocorrências — ${value}`;
      chips = [{
        label: 'Data',
        value
      }];
    } else if (filterType === 'bloco') {
      const it = D.treemap.find(s => s.name === value) || {
        value: 0,
        site: '',
        ambiente: ''
      };
      total = it.value;
      site = it.site;
      amb = it.ambiente;
      title = `Ocorrências — ${it.site} / ${it.ambiente}`;
      chips = [{
        label: 'Site',
        value: it.site
      }, {
        label: 'Ambiente',
        value: it.ambiente
      }];
    } else if (filterType === 'kpi') {
      total = extra && extra.total != null ? extra.total : 0;
      title = `Ocorrências — ${value}`;
      chips = [{
        label: 'Indicador',
        value
      }];
    } else {
      total = 0;
      title = 'Ocorrências';
    }
    return {
      total,
      title,
      chips,
      items: build(total, site, amb, filterType + value)
    };
  };
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/visao-executiva/data.js", error: String((e && e.message) || e) }); }

__ds_ns.Avatar = __ds_scope.Avatar;

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.Card = __ds_scope.Card;

__ds_ns.CardHeader = __ds_scope.CardHeader;

__ds_ns.Icon = __ds_scope.Icon;

__ds_ns.IconButton = __ds_scope.IconButton;

__ds_ns.SegmentedControl = __ds_scope.SegmentedControl;

__ds_ns.ExposureCard = __ds_scope.ExposureCard;

__ds_ns.KpiCard = __ds_scope.KpiCard;

__ds_ns.Tooltip = __ds_scope.Tooltip;

__ds_ns.Checkbox = __ds_scope.Checkbox;

__ds_ns.DateField = __ds_scope.DateField;

__ds_ns.Input = __ds_scope.Input;

__ds_ns.Select = __ds_scope.Select;

__ds_ns.Switch = __ds_scope.Switch;

})();
