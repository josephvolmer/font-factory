FF := ./fontfactory.py

# Every sheets/*.toml is a font this project knows how to build.
CONFIGS := $(wildcard sheets/*.toml)
NAMES   := $(patsubst sheets/%.toml,%,$(CONFIGS))

# Rendering text with an already-built font.
FONT     ?= fonts/MagazineCutout-Regular.ttf
TEXT     ?= input.txt
OUTPUT   ?= output.png
SIZE     ?= 96
COLOR    ?= black
BG       ?= white

.PHONY: all list clean distclean render help $(NAMES) $(addsuffix -contact,$(NAMES))

help:
	@echo "Font factory"
	@echo
	@echo "  make all             build every sheet in sheets/"
	@echo "  make <name>          build one sheet, e.g. make magazine"
	@echo "  make <name>-contact  contact sheet: check each glyph is filed right"
	@echo "  make list            show known sheets"
	@echo "  make render          render TEXT with FONT"
	@echo "  make clean           remove build intermediates"
	@echo "  make distclean       also remove the fonts this project builds"
	@echo
	@echo "  sheets: $(NAMES)"
	@echo "  render: FONT=$(FONT) TEXT=$(TEXT) OUTPUT=$(OUTPUT) SIZE=$(SIZE) COLOR=$(COLOR) BG=$(BG)"
	@echo "          (BG= for a transparent background)"

all: $(NAMES)

list:
	@for c in $(CONFIGS); do echo "  $$c"; done

# `make magazine` builds sheets/magazine.toml.
$(NAMES): %: sheets/%.toml
	@$(FF) build $< --proof

# `make magazine-contact` writes the labelled contact sheet for it.
$(addsuffix -contact,$(NAMES)): %-contact: sheets/%.toml
	@$(FF) contact $<

RENDER_ARGS = --text "$(TEXT)" --output "$(OUTPUT)" --size $(SIZE) --color "$(COLOR)"
ifneq ($(strip $(BG)),)
RENDER_ARGS += --bg "$(BG)"
endif

render:
	@$(FF) render "$(FONT)" $(RENDER_ARGS)

clean:
	rm -rf build $(OUTPUT)

# Only removes fonts this project can rebuild. A .ttf dropped into fonts/ by hand,
# with no sheet behind it, is not ours to delete.
distclean: clean
	@for c in $(CONFIGS); do rm -f "$$($(FF) path $$c)"; done
