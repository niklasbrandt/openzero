/* openZero — Planka header nav injection
 * Injects a "Go to openZero Dashboard" icon link as the first item inside
 * Planka's right header menu. Localized via document.documentElement.lang
 * (which Planka updates when the user changes their language preference).
 */
(function () {
	'use strict';

	var LABELS = {
		ar: 'الانتقال إلى openZero',
		cs: 'Přejít na openZero',
		da: 'Gå til openZero',
		de: 'Zu openZero wechseln',
		en: 'Go to openZero',
		es: 'Ir a openZero',
		fi: 'Siirry openZeroon',
		fr: 'Aller à openZero',
		hu: 'Ugrás az openZeroba',
		it: 'Vai a openZero',
		ja: 'openZero へ移動',
		ko: 'openZero로 이동',
		nb: 'Gå til openZero',
		nl: 'Ga naar openZero',
		pl: 'Przejdź do openZero',
		pt: 'Ir para openZero',
		ro: 'Mergi la openZero',
		ru: 'Перейти в openZero',
		sk: 'Prejsť na openZero',
		sv: 'Gå till openZero',
		tr: "openZero'ya git",
		uk: 'Перейти до openZero',
		zh: '前往 openZero',
	};

	function getLabel() {
		var lang = (document.documentElement.lang || navigator.language || 'en')
			.split('-')[0]
			.toLowerCase();
		return LABELS[lang] || LABELS.en;
	}

	function buildLink() {
		var label = getLabel();
		var anchor = document.createElement('a');
		anchor.id = 'oz-global-nav';
		anchor.href = '/';
		anchor.title = label;
		anchor.setAttribute('aria-label', label);
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
		text.textContent = 'openZero Dashboard';
		text.style.cssText = 'font-size:0.9em;font-weight:500;white-space:nowrap;';
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
