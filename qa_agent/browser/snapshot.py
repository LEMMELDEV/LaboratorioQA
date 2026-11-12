"""DOM snapshot injector: assigns sequential refs (e1..eN) to interactive elements.

Design rules (anti-hallucination):
- observe() CLEARS all previous refs and reassigns -> stale refs fail fast.
- The agent can only act through refs returned by the latest observation.
- Hidden elements (zero size / display:none / type=hidden) are excluded.
"""
from __future__ import annotations

SNAPSHOT_JS = r"""
(prefix) => {
  const selectors = 'a[href], button, input, select, textarea, summary, [role], [onclick], [tabindex]';
  const candidates = Array.from(document.querySelectorAll(selectors));

  const isVisible = (el) => {
    if (el.type === 'hidden') return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    const rect = el.getBoundingClientRect();
    return (rect.width > 0 || rect.height > 0);
  };

  const implicitRole = (el) => {
    const tag = el.tagName.toLowerCase();
    if (tag === 'a') return 'link';
    if (tag === 'button' || (tag === 'input' && ['submit','button'].includes(el.type))) return 'button';
    if (tag === 'input' && ['checkbox'].includes(el.type)) return 'checkbox';
    if (tag === 'input' && ['radio'].includes(el.type)) return 'radio';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'input') return 'textbox';
    if (tag === 'summary') return 'button';
    return el.getAttribute('role') || tag;
  };

  const labelOf = (el) => {
    const tag = el.tagName.toLowerCase();
    let name = '';
    if (el.getAttribute('aria-label')) name = el.getAttribute('aria-label');
    else if (el.id) {
      const lbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lbl) name = lbl.innerText.trim();
    }
    if (!name && el.labels && el.labels.length) name = el.labels[0].innerText.trim();
    if (!name && el.getAttribute('aria-labelledby')) {
      const l = document.getElementById(el.getAttribute('aria-labelledby'));
      if (l) name = l.innerText.trim();
    }
    if (!name) {
      if (tag === 'input' || tag === 'textarea') {
        name = el.getAttribute('placeholder') || el.name || el.getAttribute('title') || '';
      } else if (tag === 'select') {
        name = el.getAttribute('title') || el.name || '';
      } else if (tag === 'a' && el.querySelector('img[alt]')) {
        name = el.querySelector('img[alt]').alt;
      } else {
        name = (el.innerText || el.value || el.getAttribute('title') || '').trim();
      }
    }
    return name.replace(/\s+/g, ' ').slice(0, 80);
  };

  const formOf = (el) => {
    const form = el.closest('form');
    if (!form) return null;
    return {
      form_id: form.id || '',
      action: form.getAttribute('action') || '',
      method: (form.getAttribute('method') || 'get').toLowerCase(),
    };
  };

  // Clear stale refs, then assign fresh ones.
  document.querySelectorAll('[data-qa-ref]').forEach(el => el.removeAttribute('data-qa-ref'));

  const elements = [];
  let i = 0;
  for (const el of candidates) {
    if (!isVisible(el)) continue;
    i += 1;
    const ref = prefix + i;
    el.setAttribute('data-qa-ref', ref);

    const tag = el.tagName.toLowerCase();
    const role = implicitRole(el);
    const entry = {
      ref,
      tag,
      role,
      name: labelOf(el),
      text: (el.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 100),
    };
    if (tag === 'a') entry.href = el.getAttribute('href') || '';
    if (el.name) entry.field_name = el.name;
    if (el.value !== undefined && ['input','textarea'].includes(tag) && !['submit','button'].includes(el.type)) {
      entry.value = el.value;
    }
    if (el.disabled) entry.disabled = true;
    if (el.required) entry.required = true;
    if (el.type && tag === 'input') entry.input_type = el.type;
    if (el.min && el.min !== '') entry.min = el.min;
    if (el.max && el.max !== '') entry.max = el.max;
    if (tag === 'input' && el.type === 'checkbox') entry.checked = el.checked;
    if (tag === 'select') {
      entry.options = Array.from(el.options).map(o => (o.label || o.value).trim()).slice(0, 10);
    }
    const f = formOf(el);
    if (f) Object.assign(entry, f);
    elements.push(entry);
  }

  const headings = Array.from(document.querySelectorAll('h1, h2, h3'))
    .filter(h => h.getBoundingClientRect().width > 0)
    .map(h => (h.tagName.toLowerCase() + ': ' + h.innerText.trim()).slice(0, 90));

  const forms = Array.from(document.forms).map(form => {
    const fields = Array.from(form.querySelectorAll('input, select, textarea'))
      .filter(el => el.type !== 'hidden')
      .map(el => ({
        ref: el.getAttribute('data-qa-ref') || '',
        tag: el.tagName.toLowerCase(),
        type: el.type || '',
        name: el.name || '',
        required: !!el.required,
        checked: el.type === 'checkbox' ? el.checked : undefined,
        min: el.min || undefined,
        max: el.max || undefined,
        options: el.tagName === 'SELECT'
          ? Array.from(el.options).map(o => (o.label || o.value).trim()).slice(0, 10)
          : [],
        label: '',
      }));
    const f = { form_id: form.id || '', action: form.getAttribute('action') || '',
                method: (form.getAttribute('method') || 'get').toLowerCase(), fields };
    return f;
  });

  return {
    url: location.href,
    title: document.title,
    headings,
    elements,
    forms,
  };
}
"""
