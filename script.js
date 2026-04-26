/* ─────────────────────────────────────────────
   The Lot Legends — minimal interactions
   ───────────────────────────────────────────── */

(() => {
  /* ─── 1) Loading overlay ─── */
  const loader = document.getElementById('loader');
  if (loader) {
    const hide = () => {
      // Show for at least 700ms for poise
      const min = 700;
      const start = performance.now();
      const tick = () => {
        if (performance.now() - start >= min) loader.classList.add('is-done');
        else requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    };
    if (document.readyState === 'complete') hide();
    else window.addEventListener('load', hide);
  }

  /* ─── 2) Sticky-nav state on scroll ─── */
  const nav = document.querySelector('.nav');
  if (nav) {
    const onScroll = () => {
      if (window.scrollY > 24) nav.classList.add('is-scrolled');
      else nav.classList.remove('is-scrolled');
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  /* ─── 3) Mobile drawer ─── */
  const burger = document.getElementById('nav-burger');
  const drawer = document.getElementById('drawer');
  if (burger && drawer) {
    const close = () => {
      burger.classList.remove('is-open');
      drawer.classList.remove('is-open');
      burger.setAttribute('aria-expanded', 'false');
      drawer.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('no-scroll');
    };
    const open = () => {
      burger.classList.add('is-open');
      drawer.classList.add('is-open');
      burger.setAttribute('aria-expanded', 'true');
      drawer.setAttribute('aria-hidden', 'false');
      document.body.classList.add('no-scroll');
    };
    burger.addEventListener('click', () => {
      drawer.classList.contains('is-open') ? close() : open();
    });
    drawer.querySelectorAll('a').forEach(a => a.addEventListener('click', close));
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && drawer.classList.contains('is-open')) close();
    });
  }

  /* ─── 4) Reveal-on-scroll ─── */
  const targets = document.querySelectorAll(
    '.h2, .eyebrow, .hero__sub, .hero__cta, .hero__meta, ' +
    '.tier, .card, .steps li, .board__row, .faq__list details, .cta__inner, ' +
    '.stat, .reward-row, .form-step, .progress'
  );
  targets.forEach(el => el.classList.add('reveal'));

  if ('IntersectionObserver' in window) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry, i) => {
        if (entry.isIntersecting) {
          entry.target.style.transitionDelay = `${Math.min(i * 30, 180)}ms`;
          entry.target.classList.add('is-visible');
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });

    targets.forEach(el => io.observe(el));
  } else {
    targets.forEach(el => el.classList.add('is-visible'));
  }

  /* ─── 5) Smooth scroll for in-page anchors ─── */
  document.querySelectorAll('a[href^="#"]').forEach(a => {
    a.addEventListener('click', (e) => {
      const id = a.getAttribute('href');
      if (id.length < 2) return;
      const target = document.querySelector(id);
      if (!target) return;
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });

  /* ─── 6) Subtle parallax on hero background ─── */
  const bg = document.querySelector('.hero__bg');
  if (bg && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    window.addEventListener('scroll', () => {
      const y = Math.min(window.scrollY * 0.18, 120);
      bg.style.transform = `translate3d(0, ${y}px, 0) scale(1.05)`;
    }, { passive: true });
  }

  /* ─── 7) Animate progress bars (used on dashboard) ─── */
  const bars = document.querySelectorAll('.progress__fill[data-fill]');
  if (bars.length && 'IntersectionObserver' in window) {
    const io2 = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const el = entry.target;
          const pct = Math.max(0, Math.min(100, parseFloat(el.dataset.fill) || 0));
          requestAnimationFrame(() => { el.style.width = pct + '%'; });
          io2.unobserve(el);
        }
      });
    }, { threshold: 0.4 });
    bars.forEach(b => io2.observe(b));
  }

  /* ─── 8) Counter animation ─── */
  const counters = document.querySelectorAll('[data-count]');
  if (counters.length && 'IntersectionObserver' in window) {
    const io3 = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        const el = entry.target;
        const target = parseFloat(el.dataset.count) || 0;
        const dur = 1400;
        const start = performance.now();
        const fmt = (n) => Math.round(n).toLocaleString('en-US');
        const tick = (now) => {
          const t = Math.min(1, (now - start) / dur);
          const eased = 1 - Math.pow(1 - t, 3);
          el.textContent = fmt(target * eased);
          if (t < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
        io3.unobserve(el);
      });
    }, { threshold: 0.5 });
    counters.forEach(c => io3.observe(c));
  }

  /* ─── 9) Multi-step form (used on join page) ─── */
  const form = document.getElementById('join-form');
  if (form) {
    const steps = Array.from(form.querySelectorAll('.form-step'));
    const wrap  = form.closest('.card-panel') || document;
    const dots  = Array.from(wrap.querySelectorAll('.stepper__dot'));
    const lines = Array.from(wrap.querySelectorAll('.stepper__line'));
    let i = 0;

    const show = (n) => {
      i = Math.max(0, Math.min(steps.length - 1, n));
      steps.forEach((s, idx) => s.classList.toggle('is-active', idx === i));
      dots.forEach((d, idx) => {
        d.classList.toggle('is-active', idx === i);
        d.classList.toggle('is-done', idx < i);
      });
      lines.forEach((l, idx) => l.classList.toggle('is-done', idx < i));
      form.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };

    form.addEventListener('click', (e) => {
      const next = e.target.closest('[data-step="next"]');
      const back = e.target.closest('[data-step="back"]');
      if (next) {
        const current = steps[i];
        const required = current.querySelectorAll('[required]');
        let ok = true;
        required.forEach(r => { if (!r.value.trim()) { r.classList.add('has-error'); ok = false; } else r.classList.remove('has-error'); });
        if (ok) show(i + 1);
      }
      if (back) show(i - 1);
    });

    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const success = document.getElementById('form-success');
      if (success) {
        form.style.display = 'none';
        success.hidden = false;
        success.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    });

    show(0);
  }
})();
