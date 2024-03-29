DIST=dist
PACKAGE=keepnote_mendeley
SRCFILES=info.xml __init__.py icons/mendeleydesktop.png
CONTENTS=$(addprefix $(PACKAGE)/,$(SRCFILES))
DESTINATION=$(HOME)/.config/keepnote/extensions/$(PACKAGE)

ZIP=/usr/bin/env zip

install: $(CONTENTS)
	mkdir -p $(DESTINATION)
	cp $(CONTENTS) $(DESTINATION)/	

kne: $(DIST)/$(PACKAGE).kne

$(DIST)/$(PACKAGE).kne: $(CONTENTS) dist
	$(ZIP) $@ $(CONTENTS)

$(DIST):
	mkdir -p $(DIST)

clean:
	rm -fr $(DIST)
