prefix=/usr

all:

clean:
	fixme

install:
	install -d -m 0755 "$(DESTDIR)/$(prefix)/lib64/mirrors/plugins"
	cp -r github "$(DESTDIR)/$(prefix)/lib64/mirrors/plugins"
	find "$(DESTDIR)/$(prefix)/lib64/mirrors/plugins/github" -type f | xargs chmod 644
	find "$(DESTDIR)/$(prefix)/lib64/mirrors/plugins/github" -type d | xargs chmod 755
	find "$(DESTDIR)/$(prefix)/lib64/mirrors/plugins/github" -name "*.py" | xargs chmod 755

uninstall:
	rm -rf "$(DESTDIR)/$(prefix)/lib64/mirrors/plugins/github"

.PHONY: all clean install uninstall
