/**
 * Shared navigation bar for x-onset.
 * Auto-injects a <nav> at the top of <body> on DOMContentLoaded.
 */
(function () {
  'use strict';

  const NAV_ITEMS = [
    { label: 'Song Library', href: '/', icon: '&#9836;' },
    { label: 'Theme Editor', href: '/themes/', icon: '&#9672;' },
    { label: 'Variant Library', href: '/variants/', icon: '&#9783;' },
    { label: 'Layout Grouping', href: '/grouper', icon: '&#9638;' },
  ];

  // Song-specific tool pages that render a breadcrumb with a per-song segment
  // (Song Library › <Song> › <Tool>).
  const SONG_TOOL_PAGES = {
    '/timeline': 'Timeline',
    '/story-review': 'Story Review',
    '/phonemes-view': 'Phonemes',
    '/sweep-view': 'Sweep Results',
  };

  // Spec 045 US5: Zone D / layout-admin pages have no song context. They
  // render a collapsed breadcrumb (Song Library › <Tool>) so the user always
  // has a one-click route back to the library (FR-012).
  const ADMIN_TOOL_PAGES = {
    '/grouper': 'Layout Grouping',
    '/themes/': 'Theme Editor',
    '/variants/': 'Variant Library',
  };

  function getActivePath() {
    return window.location.pathname;
  }

  function isSongToolPage(path) {
    return SONG_TOOL_PAGES.hasOwnProperty(path);
  }

  function isAdminToolPage(path) {
    if (ADMIN_TOOL_PAGES.hasOwnProperty(path)) return true;
    // Tolerate missing/extra trailing slashes (/themes, /themes/)
    if (path !== '/' && path.endsWith('/') && ADMIN_TOOL_PAGES.hasOwnProperty(path)) return true;
    if (!path.endsWith('/') && ADMIN_TOOL_PAGES.hasOwnProperty(path + '/')) return true;
    return false;
  }

  function adminToolLabel(path) {
    if (ADMIN_TOOL_PAGES[path]) return ADMIN_TOOL_PAGES[path];
    if (ADMIN_TOOL_PAGES[path + '/']) return ADMIN_TOOL_PAGES[path + '/'];
    return '';
  }

  function buildNav() {
    const nav = document.createElement('nav');
    nav.id = 'xlight-navbar';
    nav.className = 'xlight-navbar';

    // Brand
    const brand = document.createElement('a');
    brand.href = '/';
    brand.className = 'navbar-brand';
    brand.innerHTML = 'x-<span class="onset-pulse" style="color:var(--xo-accent);text-shadow:0 0 10px var(--xo-accent)">onset</span>';
    nav.appendChild(brand);

    // Nav links
    const linksWrap = document.createElement('div');
    linksWrap.className = 'navbar-links';

    const currentPath = getActivePath();

    NAV_ITEMS.forEach(function (item) {
      const a = document.createElement('a');
      a.href = item.href;
      a.className = 'navbar-link';
      a.innerHTML = '<span class="navbar-icon">' + item.icon + '</span> ' + item.label;

      // Active state: exact match or song/admin tool pages highlight Song Library
      if (item.href === currentPath) {
        a.classList.add('active');
      } else if (item.href === '/' && isSongToolPage(currentPath)) {
        a.classList.add('active-parent');
      }

      linksWrap.appendChild(a);
    });

    nav.appendChild(linksWrap);

    // Breadcrumb for song tool pages (Song Library › Song › Tool)
    if (isSongToolPage(currentPath)) {
      const breadcrumb = document.createElement('div');
      breadcrumb.className = 'navbar-breadcrumb';
      breadcrumb.id = 'navbar-breadcrumb';

      const homeLink = document.createElement('a');
      homeLink.href = '/';
      homeLink.textContent = 'Song Library';
      breadcrumb.appendChild(homeLink);

      const sep1 = document.createElement('span');
      sep1.className = 'breadcrumb-sep';
      sep1.textContent = ' \u203A ';
      breadcrumb.appendChild(sep1);

      const songName = document.createElement('span');
      songName.className = 'breadcrumb-song';
      songName.id = 'breadcrumb-song-name';
      songName.textContent = 'Song';
      breadcrumb.appendChild(songName);

      const sep2 = document.createElement('span');
      sep2.className = 'breadcrumb-sep';
      sep2.textContent = ' \u203A ';
      breadcrumb.appendChild(sep2);

      const toolName = document.createElement('span');
      toolName.className = 'breadcrumb-tool';
      toolName.textContent = SONG_TOOL_PAGES[currentPath];
      breadcrumb.appendChild(toolName);

      nav.appendChild(breadcrumb);
    } else if (isAdminToolPage(currentPath)) {
      // Spec 045 US5: admin/Zone D pages render a collapsed breadcrumb
      // (Song Library › <Tool>) so the user can always return to /.
      const breadcrumb = document.createElement('div');
      breadcrumb.className = 'navbar-breadcrumb';
      breadcrumb.id = 'navbar-breadcrumb';

      const homeLink = document.createElement('a');
      homeLink.href = '/';
      homeLink.textContent = 'Song Library';
      breadcrumb.appendChild(homeLink);

      const sep = document.createElement('span');
      sep.className = 'breadcrumb-sep';
      sep.textContent = ' \u203A ';
      breadcrumb.appendChild(sep);

      const toolName = document.createElement('span');
      toolName.className = 'breadcrumb-tool';
      toolName.textContent = adminToolLabel(currentPath);
      breadcrumb.appendChild(toolName);

      nav.appendChild(breadcrumb);
    }

    return nav;
  }

  function inject() {
    var nav = buildNav();
    document.body.insertBefore(nav, document.body.firstChild);
    document.body.classList.add('has-navbar');
  }

  /**
   * Update the breadcrumb song name (call from page JS once the title is known).
   */
  window.xlightNavbar = {
    setSongName: function (name) {
      var el = document.getElementById('breadcrumb-song-name');
      if (el) el.textContent = name;
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
  } else {
    inject();
  }
})();
