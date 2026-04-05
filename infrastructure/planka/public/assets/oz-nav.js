/* openZero — Planka header nav injection
 * Injects a "Dashboard" link as the first item inside Planka's right header menu.
 */
(function () {
	'use strict';

	function buildLink() {
		var anchor = document.createElement('a');
		anchor.id = 'oz-global-nav';
		anchor.href = '/';
		anchor.setAttribute('aria-label', 'Dashboard');
		anchor.className = 'item';
		anchor.style.cssText = 'opacity:0.75;transition:opacity 0.15s ease;display:flex;align-items:center;gap:0.4em;margin-right:0.75em;';
		anchor.addEventListener('mouseenter', function () { anchor.style.opacity = '1'; });
		anchor.addEventListener('mouseleave', function () { anchor.style.opacity = '0.75'; });
		anchor.addEventListener('focus', function () { anchor.style.opacity = '1'; });
		anchor.addEventListener('blur', function () { anchor.style.opacity = '0.75'; });

		var icon = document.createElement('i');
		icon.setAttribute('aria-hidden', 'true');
		icon.className = 'home fitted icon';
		anchor.appendChild(icon);

		var text = document.createElement('span');
		text.textContent = 'Dashboard';
		text.style.cssText = 'font-size:0.9em;font-weight:500;white-space:nowrap;';
		text.style.setProperty('display', 'inline', 'important');
		text.style.setProperty('color', 'inherit', 'important');
		text.style.setProperty('visibility', 'visible', 'important');
		text.style.setProperty('opacity', '1', 'important');
		anchor.appendChild(text);

		return anchor;
	}

	var childObserver = null;

	function injectLink(rightMenu) {
		if (document.getElementById('oz-global-nav')) return;
		rightMenu.insertBefore(buildLink(), rightMenu.firstChild);

		// Watch only this menu's direct children so we can re-inject if React
		// ever removes our element (narrow observer — no subtree scan).
		if (!childObserver) {
			childObserver = new MutationObserver(function (mutations) {
				for (var i = 0; i < mutations.length; i++) {
					var removed = mutations[i].removedNodes;
					for (var j = 0; j < removed.length; j++) {
						if (removed[j].id === 'oz-global-nav') {
							injectLink(rightMenu);
							return;
						}
					}
				}
			});
			childObserver.observe(rightMenu, { childList: true });
		}
	}

	// Poll until Planka's React app renders the header (SPA, so DOM is dynamic).
	var attempts = 0;
	var timer = setInterval(function () {
		var rightMenu = document.querySelector('div.right.menu');
		if (rightMenu) {
			injectLink(rightMenu);
			clearInterval(timer);
		} else if (++attempts >= 150) {
			clearInterval(timer);
		}
	}, 200);
}());
