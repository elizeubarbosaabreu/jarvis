/* Jarvis Control — expõe controle de janelas por DBus para o assistente.
 * Funciona no Wayland porque roda dentro do próprio GNOME Shell.
 */
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const BUS_NAME = 'br.jarvis.Control';
const OBJECT_PATH = '/br/jarvis/Control';

// Substituído pelo install.sh com o caminho real do projeto.
const JARVIS_ROOT = '__JARVIS_ROOT__';
const JARVIS_CTL = `${JARVIS_ROOT}/jarvis-ctl`;

const IFACE_XML = `
<node>
  <interface name="br.jarvis.Control">
    <method name="List">
      <arg type="s" direction="out" name="json"/>
    </method>
    <method name="Close">
      <arg type="s" direction="in" name="app"/>
      <arg type="s" direction="out" name="result"/>
    </method>
    <method name="Minimize">
      <arg type="s" direction="in" name="app"/>
      <arg type="s" direction="out" name="result"/>
    </method>
    <method name="Unminimize">
      <arg type="s" direction="in" name="app"/>
      <arg type="s" direction="out" name="result"/>
    </method>
    <method name="Activate">
      <arg type="s" direction="in" name="app"/>
      <arg type="s" direction="out" name="result"/>
    </method>
    <method name="Maximize">
      <arg type="s" direction="in" name="app"/>
      <arg type="s" direction="out" name="result"/>
    </method>
    <method name="MinimizeAll">
      <arg type="s" direction="out" name="result"/>
    </method>
    <method name="RestoreAll">
      <arg type="s" direction="out" name="result"/>
    </method>
    <method name="ShowDesktop">
      <arg type="s" direction="out" name="result"/>
    </method>
  </interface>
</node>`;

/* Botão do painel: clique esquerdo abre o assistente; clique direito abre o
 * menu com "Abrir" e "Desligar".
 */
const JarvisButton = GObject.registerClass(
class JarvisButton extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'Jarvis', false);

        this.add_child(new St.Icon({
            icon_name: 'audio-input-microphone-symbolic',
            style_class: 'system-status-icon',
        }));

        this.menu.addAction('Abrir JARVIS', () => this._openJarvis());
        this.menu.addAction('Desligar JARVIS', () => this._stopJarvis());
    }

    vfunc_event(event) {
        const type = event.type();

        if (type === Clutter.EventType.BUTTON_PRESS) {
            if (event.get_button() === 3) {
                this.menu.toggle();
                return Clutter.EVENT_STOP;
            }
            this._openJarvis();
            return Clutter.EVENT_STOP;
        }

        if (type === Clutter.EventType.TOUCH_BEGIN) {
            this._openJarvis();
            return Clutter.EVENT_STOP;
        }

        return Clutter.EVENT_PROPAGATE;
    }

    _openJarvis() {
        try {
            GLib.spawn_command_line_async(`"${JARVIS_CTL}" open`);
        } catch (e) {
            logError(e, 'Jarvis: falha ao abrir');
        }
    }

    _stopJarvis() {
        try {
            GLib.spawn_command_line_async(`"${JARVIS_CTL}" off`);
        } catch (e) {
            logError(e, 'Jarvis: falha ao desligar');
        }
    }
});

export default class JarvisControlExtension extends Extension {
    enable() {
        this._dbus = Gio.DBusExportedObject.wrapJSObject(IFACE_XML, this);
        this._dbus.export(Gio.DBus.session, OBJECT_PATH);
        this._ownerId = Gio.bus_own_name(
            Gio.BusType.SESSION,
            BUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            null,
            null,
            null
        );

        this._button = new JarvisButton();
        Main.panel.addToStatusArea('jarvis-open', this._button, 0, 'right');
    }

    disable() {
        if (this._button) {
            this._button.destroy();
            this._button = null;
        }
        if (this._ownerId) {
            Gio.bus_unown_name(this._ownerId);
            this._ownerId = null;
        }
        if (this._dbus) {
            this._dbus.unexport();
            this._dbus = null;
        }
    }

    // --- utilidades ---------------------------------------------------
    _appName(win) {
        try {
            const tracker = Shell.WindowTracker.get_default();
            const app = tracker.get_window_app(win);
            if (app)
                return app.get_name();
        } catch (e) {
            // ignora
        }
        return win.get_wm_class() || '';
    }

    _windows() {
        const out = [];
        for (const actor of global.get_window_actors()) {
            const win = actor.meta_window;
            if (!win)
                continue;
            if (win.get_window_type() !== Meta.WindowType.NORMAL)
                continue;
            if (win.is_skip_taskbar())
                continue;
            out.push(win);
        }
        return out;
    }

    _describe(win) {
        return {
            app: this._appName(win),
            title: win.get_title() || '',
            minimized: win.minimized,
            focused: win.has_focus(),
            maximized: win.get_maximized() === Meta.MaximizeFlags.BOTH,
        };
    }

    _match(query) {
        const q = (query || '').toLowerCase().trim();
        if (!q)
            return [];
        const wins = this._windows();
        let hits = wins.filter(w => {
            const app = this._appName(w).toLowerCase();
            const title = (w.get_title() || '').toLowerCase();
            const cls = (w.get_wm_class() || '').toLowerCase();
            return (
                (app && (app.includes(q) || q.includes(app))) ||
                (title && title.includes(q)) ||
                (cls && cls.includes(q))
            );
        });
        if (hits.length === 0) {
            // tenta por pedaços (ex.: "navegador" -> "firefox")
            hits = wins.filter(w => {
                const app = this._appName(w).toLowerCase();
                return q.split(/\s+/).some(t => t.length > 2 && app.includes(t));
            });
        }
        return hits;
    }

    _result(ok, app, wins, extra) {
        return JSON.stringify({
            ok: ok,
            app: app,
            count: wins ? wins.length : 0,
            windows: wins ? wins.map(w => this._describe(w)) : [],
            ...(extra || {}),
        });
    }

    // --- métodos DBus --------------------------------------------------
    List() {
        try {
            const wins = this._windows();
            return JSON.stringify({
                ok: true,
                count: wins.length,
                windows: wins.map(w => this._describe(w)),
            });
        } catch (e) {
            return JSON.stringify({ok: false, error: String(e)});
        }
    }

    Close(app) {
        try {
            const wins = this._match(app);
            for (const w of wins)
                w.delete(global.get_current_time());
            return this._result(wins.length > 0, app, wins);
        } catch (e) {
            return JSON.stringify({ok: false, error: String(e)});
        }
    }

    Minimize(app) {
        try {
            const wins = this._match(app);
            for (const w of wins)
                w.minimize();
            return this._result(wins.length > 0, app, wins);
        } catch (e) {
            return JSON.stringify({ok: false, error: String(e)});
        }
    }

    Unminimize(app) {
        try {
            const wins = this._match(app);
            for (const w of wins)
                w.unminimize();
            return this._result(wins.length > 0, app, wins);
        } catch (e) {
            return JSON.stringify({ok: false, error: String(e)});
        }
    }

    Activate(app) {
        try {
            const wins = this._match(app);
            if (wins.length > 0) {
                const win = wins[0];
                if (win.minimized)
                    win.unminimize();
                Main.activateWindow(win);
            }
            return this._result(wins.length > 0, app, wins);
        } catch (e) {
            return JSON.stringify({ok: false, error: String(e)});
        }
    }

    Maximize(app) {
        try {
            const wins = this._match(app);
            for (const w of wins) {
                if (w.minimized)
                    w.unminimize();
                w.maximize(Meta.MaximizeFlags.BOTH);
            }
            return this._result(wins.length > 0, app, wins);
        } catch (e) {
            return JSON.stringify({ok: false, error: String(e)});
        }
    }

    MinimizeAll() {
        try {
            const wins = this._windows();
            for (const w of wins)
                w.minimize();
            return this._result(true, '', wins);
        } catch (e) {
            return JSON.stringify({ok: false, error: String(e)});
        }
    }

    RestoreAll() {
        try {
            const wins = this._windows();
            for (const w of wins)
                w.unminimize();
            return this._result(true, '', wins);
        } catch (e) {
            return JSON.stringify({ok: false, error: String(e)});
        }
    }

    ShowDesktop() {
        return this.MinimizeAll();
    }
}
