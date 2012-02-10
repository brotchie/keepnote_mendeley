"""

    KeepNote Mendeley Integration

"""

#
#  KeepNote - Mendeley Integration
#  Copyright (c) 2012 James Brotchie
#  Author: James Brotchie <brotchie@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301, USA.
#


# python imports
import os
import sqlite3
from ConfigParser import ConfigParser

# keepnote imports
from keepnote.gui import extension
from keepnote.gui.popupwindow import PopupWindow

# pygtk imports
try:
    import pygtk
    pygtk.require('2.0')
    from gtk import gdk
    import gtk.glade
    import gobject

    from keepnote.gui import dialog_app_options
except ImportError:
    # do not fail on gtk import error,
    # extension should be usable for non-graphical uses
    pass

# Location where our .kne was extracted. Lets us find
# where the Mendeley icon is location.
EXTENSION_DIRECTORY = os.path.dirname(__file__)
EXTENSION_ICON_DIRECTORY = os.path.join(EXTENSION_DIRECTORY, 'icons')
MENDELEY_ICON_NAME = 'mendeleydesktop.png'
MENDELEY_ICON_PATH = os.path.join(EXTENSION_ICON_DIRECTORY, os.path.join('mendeleydesktop.png'))

# Nodes linking to Mendeley documents are market
# with this content type.
CONTENT_TYPE_MENDELEY_LINK = 'mendeley/link'

# The UUID of each document is stored on Mendeley
# keepnote nodes with the attribute.
MENDELEY_UUID_ATTR = 'mendeley-uuid'

# On Linux we can usually find the Mendeley sqlite3 database
# at this location.
EXPECTED_MENDELEY_SQLITE_DIR = os.path.expanduser('~/.local/share/data/Mendeley Ltd./Mendeley Desktop')
EXPECTED_MENDELEY_CONFIG_PATH = os.path.expanduser('~/.config/Mendeley Ltd./Mendeley Desktop.conf')

def find_mendeley_sqlite_path():
    """
    Returns the path to the Mendeley sqlite3 database if in
    standard location, otherwise returns None.

    """
    try:
        if os.path.exists(EXPECTED_MENDELEY_CONFIG_PATH):
            cp = ConfigParser()
            cp.read(EXPECTED_MENDELEY_CONFIG_PATH)

            email = cp.get('MendeleyWeb', 'userEmail')

            candidate_path = os.path.join(EXPECTED_MENDELEY_SQLITE_DIR, '%s@www.mendeley.com.sqlite' % (email,))
            if os.path.exists(candidate_path):
                return candidate_path
    except StandardError:
        pass

    return None

class Extension(extension.Extension):
    def __init__(self, app):
        super(Extension, self).__init__(app)
        self._app = app
        self._picker = None

        self.config = {}
        self._mendeley = None
        
        self.enabled.add(self.on_enabled)

    def on_enabled(self, ext):
        self.config = self.load_config()
        if not self.config.get('databasepath'):
            self.config['databasepath'] = find_mendeley_sqlite_path()
        self._mendeley = MendeleyDatabaseInterface(self.config.get('databasepath'))

    def get_depends(self):
        return [("keepnote", ">=", (0, 7, 7))]
    
    def on_add_ui(self, window):
        self._picker = ReferencePickerPopup(window, self._mendeley)
        self._picker.connect('pick-reference', self.on_pick_reference)

        self._connect_viewer_signals(window.viewer.get_current_viewer())

        # Tiny hack here so that we can connect up signals for double
        # clicking on the treeview and listview for all open tabs.
        window.viewer._tabs.connect('page-added', self._on_tab_added)

        self.add_action(window, "Mendeley", "Add Mendeley Reference...",
                        lambda w: self.on_add_mendeley_reference(
                window, window.get_notebook()), accel="<ctrl><shift>b")
        
        self.add_ui(window,
            """
            <ui>
            <menubar name="popup_menus">
                <menu action="treeview_popup">
                    <placeholder name="New">
                        <menuitem action="Mendeley"/>
                    </placeholder>
                </menu>
                <menu action="listview_popup">
                    <placeholder name="New">
                        <menuitem action="Mendeley"/>
                    </placeholder>
                </menu>
            </menubar>
            </ui>
            """)

    
    def on_add_mendeley_reference(self, window, notebook):
        if notebook is None:
            return

        # Ensure we've loaded the Mendeley 16x16 icon
        # into the icon store.
        if MENDELEY_ICON_NAME not in notebook.get_icons():
            notebook.install_icon(MENDELEY_ICON_PATH)

        current = window.get_current_node()
        self._picker.pick_reference_for(current)

    def on_pick_reference(self, picker, reference, parent):
        """
        Once a reference has been picked create a new
        node for it and set the icon to the Mendeley 16x16
        icon.

        """
        child = parent.new_child(CONTENT_TYPE_MENDELEY_LINK, reference.as_text_reference())
        child.set_attr('icon', MENDELEY_ICON_NAME)
        child.set_attr(MENDELEY_UUID_ATTR, reference.uuid)

    def _on_tab_added(self, tabs, child, page_num):
        """
        A new tab being created is the closest proxy
        and extension has to finding out when a new
        Notebook has been opened.

        """
        self._connect_viewer_signals(child)

    def _on_activate_node(self, view, node):
        """
        If the double-clicked node is a Mendeley link
        then lookup the referenced file by its uuid
        in the Mendeley database and launch the file
        viewer.

        """
        if node.get_attr('content_type') == CONTENT_TYPE_MENDELEY_LINK:
            uuid = node.get_attr(MENDELEY_UUID_ATTR)
            if uuid:
                localurl = self._mendeley.get_reference_path_by_uuid(uuid)
                if localurl:
                    self._app.run_external_app('file_launcher', localurl)

    def _connect_viewer_signals(self, viewer):
        """
        Registers to be notified when any node within a
        three_pane_viewer is double-clicked.

        """
        viewer.listview.connect('activate-node', self._on_activate_node)
        viewer.treeview.connect('activate-node', self._on_activate_node)

    # ===================================
    #  Config Handling

    def on_add_options_ui(self, dialog):
        dialog.add_section(MendeleySection('mendeley',
                                           dialog, self._app,
                                           self),
                           'extensions')

    def on_remove_options_ui(self, dialog):
        dialog.remove_section('mendeley')


    def get_config_file(self):
        return self.get_data_file('config')

    def load_config(self):
        configpath = self.get_config_file()
        cp = ConfigParser()

        if os.path.exists(configpath):
            cp.read(configpath)

        config = {}
        if cp.has_section('Mendeley'):
            config.update(dict(cp.items('Mendeley')))
        return config

    def save_config(self, config):
        configpath = self.get_config_file()

        cp = ConfigParser()
        cp.add_section('Mendeley')
        for k, v in config.iteritems():
            cp.set('Mendeley', k, v)

        cp.write(file(configpath, 'w+'))

        if config.get('databasepath'):
            self._mendeley.path = config.get('databasepath')

class MendeleyDatabaseInterface(object):
    def __init__(self, path=None):
        self.path = path

    def get_references(self):
        """
        Retrieves all references from the Mendeley database
        and returns a list of MendeleyReferences.

        """
        with sqlite3.connect(self.path) as db:
            c = db.execute("SELECT Documents.uuid, group_concat(DocumentContributors.lastName, ', ') as authors, Documents.year, Documents.title FROM DocumentContributors, Documents WHERE Documents.id=DocumentContributors.documentId group by Documents.year, Documents.title ORDER BY authors;")
            return [MendeleyReference(*row) for row in c]

    def get_reference_path_by_uuid(self, uuid):
        """
        For a given document UUID, looks up and returns
        its first local file url.

        """
        with sqlite3.connect(self.path) as db:
            c = db.execute("SELECT Files.localUrl FROM Files, DocumentFiles, Documents WHERE Files.hash = DocumentFiles.hash AND DocumentFiles.documentId = Documents.id AND Documents.uuid=? LIMIT 1", (uuid,))
            row = c.fetchone()
            if row:
                localurl, = row
                return localurl
            else:
                return None

class MendeleyReference(object):
    """
    Simple class to hold a Mendeley document's reference
    data.

    """
    def __init__(self, uuid, authors, year, title):
        self.uuid = uuid
        self.authors = authors
        self.year = year
        self.title = title

    def as_text_reference(self):
        if self.year:
            return '%s - %d - %s' % (self.authors, self.year, self.title)
        else:
            return '%s - %s' % (self.authors, self.title)

class ReferencePickerPopup(gtk.Window):
    """
    Displays a popup list populated from the Mendeley database.

    """
    def __init__(self, parent, mendeley):
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        self.set_decorated(False)
        self.set_transient_for(parent.get_toplevel())

        self._parent = parent
        self._targetnode = None
        self._mendeley = mendeley

        self._frame = gtk.Frame()

        self.set_size_request(600,400)

        self._liststore = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_PYOBJECT)

        self._treeview = gtk.TreeView(self._liststore)
        self._treeview.set_headers_visible(False)
        self._name_column = gtk.TreeViewColumn("Reference")

        self._treeview.append_column(self._name_column)
        self._name_cell = gtk.CellRendererText()
        self._name_column.pack_start(self._name_cell, True)
        self._name_column.add_attribute(self._name_cell, 'text', 0)

        self._treeview.show()
        self._frame.add(self._treeview)
        self._frame.show()
        self.add(self._frame)

        self._treeview.connect('key-release-event', self._on_key_release)
        self._treeview.connect('row-activated', self._on_row_activated)

        self.hide()

    def pick_reference_for(self, node):
        self._targetnode = node
        self.populate_references()
        self.show()

    def populate_references(self):
        self._liststore.clear()
        for ref in self._mendeley.get_references():
            self._liststore.append((ref.as_text_reference(), ref))

    def _on_key_release(self, widget, event):
        if event.keyval == gtk.keysyms.Escape:
            self.hide()

    def _on_row_activated(self, treeview, path, view_column):
        model, iter = self._treeview.get_selection().get_selected()
        selected_reference = model.get_value(iter, 1)
        self.emit('pick-reference', selected_reference, self._targetnode)
        self._targetnode = None
        self.hide()

class MendeleySection(dialog_app_options.Section):
    def __init__(self, key, dialog, app, ext,
                 label=u'Mendeley',
                 icon=MENDELEY_ICON_PATH):
        super(MendeleySection, self).__init__(key, dialog, app, label, icon)

        self.ext = ext
        self.app = app
        w = self.get_default_widget()
        v = gtk.VBox(False, 5)
        w.add(v)

        table = gtk.Table(1, 2)
        v.pack_start(table, True, True, 0)

        label = gtk.Label('Mendeley DB:')
        table.attach(label, 0, 1, 0, 1,
                     xoptions=0, yoptions=0,
                     xpadding=2, ypadding=2)
        self.pathentry = gtk.Entry()
        self.pathentry.set_size_request(340,-1)
        table.attach(self.pathentry, 1, 2, 0, 1,
                     xoptions=gtk.EXPAND|gtk.FILL, yoptions=0,
                     xpadding=2, ypadding=2)
        button = gtk.Button('Set Mendeley DB...')
        button.connect('clicked', self._on_set_mendeley_db)
        table.attach(button, 1, 2, 1, 2,
                     xoptions=0, yoptions=0,
                     xpadding=2, ypadding=2)
        w.show_all()

    def load_options(self, app):
        self.pathentry.set_text(self.ext.config.get('databasepath', ''))

    def save_options(self, app):
        dbpath = self.pathentry.get_text()
        if dbpath:
            self.ext.config['databasepath'] = dbpath
        self.ext.save_config(self.ext.config)

    def _on_set_mendeley_db(self, w):
        dialog = gtk.FileChooserDialog('Select Mendeley Database',
                    action=gtk.FILE_CHOOSER_ACTION_OPEN,
                    buttons=('Cancel', gtk.RESPONSE_CANCEL,
                             'Select Database', gtk.RESPONSE_OK),
                    parent=self.dialog.dialog)
        response = dialog.run()
        if response == gtk.RESPONSE_OK and dialog.get_filename():
            self.pathentry.set_text(dialog.get_filename())

        dialog.destroy()

try:
    gobject.type_register(ReferencePickerPopup)
    gobject.signal_new('pick-reference', ReferencePickerPopup,
                       gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
                       (object, object))
except:
    pass
