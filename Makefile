PREFIX?=/usr/local
BINDIR?=$(PREFIX)/bin
LIBDIR?=$(PREFIX)/lib
SHAREDIR?=$(PREFIX)/share/sourcehut

SERVICE=hub.sr.ht
STATICDIR=$(SHAREDIR)/static/$(SERVICE)

SASSC?=sassc
SASSC_INCLUDE=-I$(SHAREDIR)/scss/

BINARIES=\
	$(SERVICE)-api

all: all-bin all-share

install: install-bin install-share

clean: clean-bin clean-share

all-bin: $(BINARIES)

all-share: static/main.min.css

install-bin: all-bin
	mkdir -p $(BINDIR)
	for bin in $(BINARIES); \
	do \
		install -Dm755 $$bin $(BINDIR)/; \
	done

install-share: all-share
	mkdir -p $(STATICDIR)
	install -Dm644 static/*.css $(STATICDIR)
	install -Dm644 api/graph/schema.graphqls $(SHAREDIR)/$(SERVICE).graphqls

clean-bin:
	rm -f $(BINARIES)

clean-share:
	rm -f static/main.min.css static/main.css

.PHONY: all all-bin all-share
.PHONY: install install-bin install-share
.PHONY: clean clean-bin clean-share

static/main.css: scss/main.scss
	mkdir -p $(@D)
	$(SASSC) $(SASSC_INCLUDE) $< $@

static/main.min.css: static/main.css
	minify -o $@ $<
	cp $@ $(@D)/main.min.$$(sha256sum $@ | cut -c1-8).css

api/graph/api/generated.go: api/graph/schema.graphqls api/graph/generate.go go.sum
	cd api && go generate ./graph

$(SERVICE)-api: api/graph/api/generated.go
	go build -o $@ ./api

# Always rebuild
.PHONY: $(BINARIES)
