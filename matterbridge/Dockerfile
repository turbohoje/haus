FROM luligu/matterbridge:latest

# The plugin is installed into the global node_modules, next to matterbridge
# itself. That placement is what makes `import ... from 'matterbridge'` resolve:
# Node walks up from /…/node_modules/matterbridge-haus and finds matterbridge as
# a sibling. It is also where matterbridge looks when resolving a plugin by bare
# name, and it keeps the plugin out of the "local plugin" path that would make
# matterbridge run `npm link` against it on every boot.
#
# Copy-then-install rather than `npm install -g ./plugin`: npm 7+ *symlinks* a
# local directory install and never installs its dependencies, which would leave
# `ws` missing at runtime.
COPY plugin/ /plugin-src/
RUN PLUGIN_DIR="$(npm root -g)/matterbridge-haus" && \
    mkdir -p "$PLUGIN_DIR" && \
    cp -r /plugin-src/. "$PLUGIN_DIR/" && \
    cd "$PLUGIN_DIR" && \
    npm install --omit=dev --no-fund --no-audit && \
    rm -rf /plugin-src && \
    npm cache clean --force

COPY entrypoint.sh /haus-entrypoint.sh
RUN chmod +x /haus-entrypoint.sh

ENTRYPOINT ["/haus-entrypoint.sh"]
# --novirtual: matterbridge otherwise adds its own "Restart/Update Matterbridge"
# on/off endpoints, which Google Home would show as two extra controllable plugs.
CMD ["matterbridge", "--docker", "--novirtual"]
