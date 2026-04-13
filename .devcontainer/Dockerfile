FROM node:20

ARG TZ
ENV TZ="$TZ"

ARG CLAUDE_CODE_VERSION=latest

# Install basic development tools and iptables/ipset
RUN apt-get update && apt-get install -y --no-install-recommends \
  less \
  git \
  procps \
  sudo \
  fzf \
  zsh \
  man-db \
  unzip \
  gnupg2 \
  gh \
  iptables \
  ipset \
  iproute2 \
  dnsutils \
  aggregate \
  jq \
  nano \
  vim \
  python3 \
  python3-dev \
  python3-pip \
  python3-venv \
  ffmpeg \
  build-essential \
  cmake \
  libarmadillo-dev \
  libaubio-dev \
  libfftw3-dev \
  libsamplerate0-dev \
  libsndfile1-dev \
  libyaml-dev \
  pkg-config \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

# xLights headless rendering dependencies (amd64 only — arm64 uses SSH to host)
RUN ARCH=$(dpkg --print-architecture) && \
  if [ "$ARCH" = "amd64" ]; then \
    apt-get update && apt-get install -y --no-install-recommends \
      xvfb libfuse2 libgtk-3-0 freeglut3 \
      libgstreamer1.0-0 libgstreamer-plugins-base1.0-0 \
      libsdl2-2.0-0 mesa-utils libgl1-mesa-dri libgl1-mesa-glx \
    && apt-get clean && rm -rf /var/lib/apt/lists/*; \
  fi

# Ensure default node user has access to /usr/local/share
RUN mkdir -p /usr/local/share/npm-global && \
  chown -R node:node /usr/local/share

ARG USERNAME=node

# Persist bash history.
RUN SNIPPET="export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
  && mkdir /commandhistory \
  && touch /commandhistory/.bash_history \
  && chown -R $USERNAME /commandhistory

# Set `DEVCONTAINER` environment variable to help with orientation
ENV DEVCONTAINER=true

# Create workspace and config directories and set permissions
RUN mkdir -p /workspace /home/node/.claude && \
  chown -R node:node /workspace /home/node/.claude

WORKDIR /workspace

ARG GIT_DELTA_VERSION=0.18.2
RUN ARCH=$(dpkg --print-architecture) && \
  wget "https://github.com/dandavison/delta/releases/download/${GIT_DELTA_VERSION}/git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb" && \
  sudo dpkg -i "git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb" && \
  rm "git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb"

# Set up non-root user
USER node

# Install global packages
ENV NPM_CONFIG_PREFIX=/usr/local/share/npm-global
ENV PATH=$PATH:/usr/local/share/npm-global/bin

# Set the default shell to zsh rather than sh
ENV SHELL=/bin/zsh

# Set the default editor and visual
ENV EDITOR=nano
ENV VISUAL=nano

# Default powerline10k theme
ARG ZSH_IN_DOCKER_VERSION=1.2.0
RUN sh -c "$(wget -O- https://github.com/deluan/zsh-in-docker/releases/download/v${ZSH_IN_DOCKER_VERSION}/zsh-in-docker.sh)" -- \
  -p git \
  -p fzf \
  -a "source /usr/share/doc/fzf/examples/key-bindings.zsh" \
  -a "source /usr/share/doc/fzf/examples/completion.zsh" \
  -a "export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
  -x

# Install Claude
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}

# Install numpy first (vamp's setup.py imports numpy at build time)
RUN pip3 install --break-system-packages --no-cache-dir "numpy>=1.24,<2"

# Install Python project dependencies
RUN pip3 install --break-system-packages --no-cache-dir \
  "click>=8.0" \
  "scipy>=1.11" \
  "soundfile>=0.12" \
  "flask>=3.0" \
  "questionary>=2.0" \
  "rich>=13.0" \
  "librosa>=0.10" \
  "mutagen>=1.47" \
  "lyricsgenius>=3.0" \
  "vamp" \
  "demucs" \
  "Cython" \
  "patchelf" \
  "pytest"

# Install madmom and patch for Python 3.11 compatibility
RUN pip3 install --break-system-packages --no-cache-dir madmom && \
  MADMOM_DIR=$(pip3 show madmom | grep '^Location:' | cut -d' ' -f2)/madmom && \
  sed -i 's/from collections import MutableSequence/from collections.abc import MutableSequence/' "$MADMOM_DIR/processors.py" && \
  find "$MADMOM_DIR" -name "*.py" ! -path "*__pycache__*" -exec sed -i \
    -e 's/np\.float\b/np.float64/g' \
    -e 's/np\.int\b/np.int64/g' \
    -e 's/np\.bool\b/np.bool_/g' \
    -e 's/np\.complex\b/np.complex128/g' \
    -e 's/np\.str\b/np.str_/g' \
    -e 's/np\.object\b/object/g' \
    {} +

# ── Vamp Plugins ─────────────────────────────────────────────────────────────
# On x86_64: download pre-built binaries
# On arm64: build from source (no pre-built binaries available)
USER root
RUN mkdir -p /usr/local/lib/vamp && \
  ARCH=$(dpkg --print-architecture) && \
  if [ "$ARCH" = "amd64" ]; then \
    cd /tmp && \
    # QM Vamp Plugins
    (wget -q -T 15 --read-timeout=15 --tries=1 "https://code.soundsoftware.ac.uk/attachments/download/2588/qm-vamp-plugins-linux64-v1.8.0.tar.gz" -O qm.tar.gz && \
      tar -xzf qm.tar.gz && \
      cp qm-vamp-plugins-linux64-v1.8.0/*.so /usr/local/lib/vamp/ && \
      cp qm-vamp-plugins-linux64-v1.8.0/*.cat /usr/local/lib/vamp/ && \
      cp qm-vamp-plugins-linux64-v1.8.0/*.n3 /usr/local/lib/vamp/ && \
      rm -rf qm.tar.gz qm-vamp-plugins-linux64-v1.8.0 || echo "WARN: QM Vamp Plugins download failed, skipping") && \
    # pYIN
    (wget -q -T 15 --read-timeout=15 --tries=1 "https://code.soundsoftware.ac.uk/attachments/download/1741/pyin-linux64-v1.2.2.tar.gz" -O pyin.tar.gz && \
      tar -xzf pyin.tar.gz && \
      cp pyin-linux64-v1.2.2/*.so /usr/local/lib/vamp/ && \
      cp pyin-linux64-v1.2.2/*.cat /usr/local/lib/vamp/ && \
      cp pyin-linux64-v1.2.2/*.n3 /usr/local/lib/vamp/ && \
      rm -rf pyin.tar.gz pyin-linux64-v1.2.2 || echo "WARN: pYIN download failed, skipping") && \
    # NNLS-Chroma (Chordino)
    (wget -q -T 15 --read-timeout=15 --tries=1 "https://code.soundsoftware.ac.uk/attachments/download/1576/nnls-chroma-linux64-v1.1.tar.gz" -O nnls.tar.gz && \
      tar -xzf nnls.tar.gz && \
      cp nnls-chroma-linux64-v1.1/*.so /usr/local/lib/vamp/ && \
      cp nnls-chroma-linux64-v1.1/*.cat /usr/local/lib/vamp/ && \
      cp nnls-chroma-linux64-v1.1/*.n3 /usr/local/lib/vamp/ && \
      rm -rf nnls.tar.gz nnls-chroma-linux64-v1.1 || echo "WARN: NNLS-Chroma download failed, skipping") && \
    # BeatRoot
    (wget -q -T 15 --read-timeout=15 --tries=1 "https://code.soundsoftware.ac.uk/attachments/download/1744/beatroot-vamp-linux64-v1.0.2.tar.gz" -O beatroot.tar.gz && \
      tar -xzf beatroot.tar.gz && \
      cp beatroot-vamp-linux64-v1.0.2/*.so /usr/local/lib/vamp/ && \
      cp beatroot-vamp-linux64-v1.0.2/*.cat /usr/local/lib/vamp/ && \
      cp beatroot-vamp-linux64-v1.0.2/*.n3 /usr/local/lib/vamp/ && \
      rm -rf beatroot.tar.gz beatroot-vamp-linux64-v1.0.2 || echo "WARN: BeatRoot download failed, skipping") && \
    # Vamp Plugin Pack (x86-64 installer — includes segmentino, silvet, aubio, tempogram, BBC)
    (wget -q -T 30 --read-timeout=30 --tries=1 "https://code.soundsoftware.ac.uk/attachments/download/2690/vamp-plugin-pack-linux64-v2.0.tar.gz" -O pack.tar.gz && \
      tar -xzf pack.tar.gz && \
      cp vamp-plugin-pack-linux64-v2.0/*.so /usr/local/lib/vamp/ && \
      cp vamp-plugin-pack-linux64-v2.0/*.cat /usr/local/lib/vamp/ 2>/dev/null; \
      cp vamp-plugin-pack-linux64-v2.0/*.n3 /usr/local/lib/vamp/ 2>/dev/null; \
      rm -rf pack.tar.gz vamp-plugin-pack-linux64-v2.0 || echo "WARN: Vamp Plugin Pack download failed, skipping"); \
  else \
    echo "Building Vamp plugins from source for $ARCH..." && \
    cd /tmp && \
    # 1. Vamp Plugin SDK
    git clone --depth 1 https://github.com/c4dm/vamp-plugin-sdk.git && \
    cd vamp-plugin-sdk && \
    ./configure --prefix=/usr/local && make -j$(nproc) && make install 2>/dev/null; \
    cd /tmp && \
    # 2. QM DSP Library
    git clone --depth 1 https://github.com/c4dm/qm-dsp.git && \
    cd qm-dsp && \
    sed 's/-msse -msse2 -mfpmath=sse//' build/linux/Makefile.linux64 > /tmp/qm-dsp-mk && \
    make -f /tmp/qm-dsp-mk -j$(nproc) && \
    cd /tmp && \
    # 3. QM Vamp Plugins
    git clone --depth 1 https://github.com/c4dm/qm-vamp-plugins.git && \
    cd qm-vamp-plugins && \
    mkdir -p lib && ln -sf /tmp/qm-dsp lib/qm-dsp && ln -sf /tmp/vamp-plugin-sdk lib/vamp-plugin-sdk && \
    sed 's/-msse -msse2 -mfpmath=sse//' build/linux/Makefile.linux64 > /tmp/qm-vamp-mk && \
    make -f /tmp/qm-vamp-mk -j$(nproc) && \
    cp qm-vamp-plugins.so qm-vamp-plugins.cat /usr/local/lib/vamp/ && \
    cp qm-vamp-plugins.n3 /usr/local/lib/vamp/ 2>/dev/null; \
    cd /tmp && \
    # 4. Boost headers (for nnls-chroma and pyin)
    wget -q "https://github.com/boostorg/boost/releases/download/boost-1.87.0/boost-1.87.0-b2-nodocs.tar.gz" -O boost.tar.gz && \
    tar xzf boost.tar.gz && \
    # 5. NNLS-Chroma (Chordino)
    git clone --depth 1 https://github.com/c4dm/nnls-chroma.git && \
    cd nnls-chroma && rm -f *.o && \
    make -f Makefile.linux \
      VAMP_SDK_DIR=/tmp/vamp-plugin-sdk \
      BOOST_ROOT=/tmp/boost-1.87.0 \
      LDFLAGS="-shared -L/tmp/vamp-plugin-sdk -Wl,--version-script=vamp-plugin.map" \
      -j$(nproc) && \
    g++ -o nnls-chroma.so *.o \
      /tmp/vamp-plugin-sdk/src/vamp-sdk/PluginAdapter.o \
      /tmp/vamp-plugin-sdk/src/vamp-sdk/RealTime.o \
      /tmp/vamp-plugin-sdk/src/vamp-sdk/FFT.o \
      -shared -Wl,--version-script=vamp-plugin.map && \
    cp nnls-chroma.so /usr/local/lib/vamp/ && \
    cp nnls-chroma.cat /usr/local/lib/vamp/ 2>/dev/null; \
    cp nnls-chroma.n3 /usr/local/lib/vamp/ 2>/dev/null; \
    cd /tmp && \
    # 6. Segmentino (needs armadillo, qm-dsp, nnls-chroma, vamp-sdk at root level)
    git clone --depth 1 https://github.com/c4dm/segmentino.git && \
    cd segmentino && \
    ln -sf /tmp/qm-dsp qm-dsp && \
    ln -sf /tmp/nnls-chroma nnls-chroma && \
    ln -sf /tmp/vamp-plugin-sdk vamp-plugin-sdk && \
    sed -i 's|-Iarmadillo-3.900.4/include|-I/usr/include|' Makefile.inc && \
    sed -i "/^CFLAGS/ s|\$| -I/tmp/boost-1.87.0|" Makefile.inc && \
    touch .repoint.point && \
    make -f Makefile.linux \
      LDFLAGS="-shared -Wl,-Bsymbolic -Wl,--version-script=segmentino/vamp-plugin.map -larmadillo" \
      -j$(nproc) && \
    cp segmentino.so segmentino.cat /usr/local/lib/vamp/ && \
    cp segmentino.n3 /usr/local/lib/vamp/ 2>/dev/null; \
    cd /tmp && \
    # 7. BBC Vamp Plugins
    git clone --depth 1 https://github.com/bbc/bbc-vamp-plugins.git && \
    cd bbc-vamp-plugins && \
    make -f Makefile.linux VAMP_SDK_DIR=/tmp/vamp-plugin-sdk -j$(nproc) && \
    cp bbc-vamp-plugins.so /usr/local/lib/vamp/ && \
    cp bbc-vamp-plugins.cat /usr/local/lib/vamp/ && \
    cp bbc-vamp-plugins.n3 /usr/local/lib/vamp/ 2>/dev/null; \
    cd /tmp && \
    # 8. pYIN
    git clone --depth 1 https://github.com/c4dm/pyin.git && \
    cd pyin && \
    make -f Makefile.linux64 plugin \
      CFLAGS="-O3 -fPIC -I/tmp/boost-1.87.0 -I/tmp/vamp-plugin-sdk" \
      PLUGIN_LDFLAGS="-shared -Wl,--version-script=vamp-plugin.map /tmp/vamp-plugin-sdk/src/vamp-sdk/PluginAdapter.o /tmp/vamp-plugin-sdk/src/vamp-sdk/RealTime.o /tmp/vamp-plugin-sdk/src/vamp-sdk/FFT.o" \
      -j$(nproc) && \
    cp pyin.so /usr/local/lib/vamp/ && \
    cp pyin.cat /usr/local/lib/vamp/ 2>/dev/null; \
    cp pyin.n3 /usr/local/lib/vamp/ 2>/dev/null; \
    cd /tmp && \
    # 9. BeatRoot
    git clone --depth 1 https://github.com/c4dm/beatroot-vamp.git && \
    cd beatroot-vamp && \
    make -f Makefile.linux VAMP_SDK_DIR=/tmp/vamp-plugin-sdk -j$(nproc) && \
    g++ -o beatroot-vamp.so *.o \
      /tmp/vamp-plugin-sdk/src/vamp-sdk/PluginAdapter.o \
      /tmp/vamp-plugin-sdk/src/vamp-sdk/RealTime.o \
      /tmp/vamp-plugin-sdk/src/vamp-sdk/FFT.o \
      -shared -Wl,--version-script=vamp-plugin.map && \
    cp beatroot-vamp.so /usr/local/lib/vamp/ && \
    cp beatroot-vamp.cat /usr/local/lib/vamp/ 2>/dev/null; \
    cp beatroot-vamp.n3 /usr/local/lib/vamp/ 2>/dev/null; \
    cd /tmp && \
    # 10. vamp-aubio (onset/tempo/note detection)
    git clone --depth 1 https://github.com/aubio/vamp-aubio-plugins.git && \
    cd vamp-aubio-plugins && \
    g++ -shared -fPIC -O3 -o vamp-aubio.so \
      -I/tmp/vamp-plugin-sdk plugins/*.cpp libmain.cpp \
      /tmp/vamp-plugin-sdk/src/vamp-sdk/PluginAdapter.o \
      /tmp/vamp-plugin-sdk/src/vamp-sdk/RealTime.o \
      /tmp/vamp-plugin-sdk/src/vamp-sdk/FFT.o \
      $(pkg-config --cflags --libs aubio) && \
    cp vamp-aubio.so /usr/local/lib/vamp/ && \
    cp vamp-aubio.cat vamp-aubio.n3 /usr/local/lib/vamp/ 2>/dev/null; \
    cd /tmp && \
    # 11. Silvet (note transcription — strip all SSE flags from submodules too)
    git clone --depth 1 --recursive https://github.com/cannam/silvet.git && \
    cd silvet && \
    find . -name "Makefile*" -exec sed -i 's/-msse //g; s/-msse2 //g; s/-mfpmath=sse //g' {} \; && \
    sed -i 's|I../vamp-plugin-sdk/|I/tmp/vamp-plugin-sdk/|' Makefile.linux && \
    make -f Makefile.linux -j$(nproc) && \
    cp silvet.so /usr/local/lib/vamp/ && \
    cp silvet.cat silvet.n3 /usr/local/lib/vamp/ 2>/dev/null; \
    cd /tmp && \
    # 12. Tempogram
    git clone --depth 1 https://github.com/c4dm/vamp-tempogram.git && \
    cd vamp-tempogram && \
    sed -i 's/-msse -msse2 -mfpmath=sse//' Makefile.linux && \
    make -f Makefile.linux VAMP_SDK_DIR=/tmp/vamp-plugin-sdk -j$(nproc) && \
    g++ -o tempogram.so *.o \
      /tmp/vamp-plugin-sdk/src/vamp-sdk/PluginAdapter.o \
      /tmp/vamp-plugin-sdk/src/vamp-sdk/RealTime.o \
      /tmp/vamp-plugin-sdk/src/vamp-sdk/FFT.o \
      -shared && \
    cp tempogram.so /usr/local/lib/vamp/ && \
    cp tempogram.cat tempogram.n3 /usr/local/lib/vamp/ 2>/dev/null; \
    # Cleanup build artifacts
    cd / && rm -rf /tmp/vamp-plugin-sdk /tmp/qm-dsp /tmp/qm-vamp-plugins \
      /tmp/nnls-chroma /tmp/segmentino /tmp/bbc-vamp-plugins /tmp/pyin \
      /tmp/beatroot-vamp /tmp/vamp-aubio-plugins /tmp/silvet /tmp/vamp-tempogram \
      /tmp/boost* /tmp/qm-dsp-mk /tmp/qm-vamp-mk; \
  fi

ENV VAMP_PATH=/usr/local/lib/vamp
USER node

# ── Essentia (built from source — no pre-built wheel for arm64) ──────────────
RUN ARCH=$(dpkg --print-architecture) && \
  if [ "$ARCH" = "arm64" ]; then \
    cd /tmp && \
    # Eigen3 headers (essentia dependency, header-only)
    git clone --depth 1 --branch 3.4.0 https://gitlab.com/libeigen/eigen.git /tmp/eigen && \
    mkdir -p /home/node/.local/include && \
    cp -r /tmp/eigen/Eigen /home/node/.local/include/ && \
    cp -r /tmp/eigen/unsupported /home/node/.local/include/ && \
    mkdir -p /home/node/.local/share/pkgconfig && \
    printf 'prefix=/home/node/.local\nincludedir=${prefix}/include\nName: Eigen3\nVersion: 3.4.0\nDescription: Eigen3\nCflags: -I${includedir}\n' \
      > /home/node/.local/share/pkgconfig/eigen3.pc && \
    # Build essentia
    git clone --depth 1 https://github.com/MTG/essentia.git /tmp/essentia && \
    cd /tmp/essentia && \
    PKG_CONFIG_PATH=/home/node/.local/share/pkgconfig:$PKG_CONFIG_PATH \
      python3 waf configure --with-python --prefix=/home/node/.local --fft=FFTW && \
    python3 waf build -j$(nproc) && \
    python3 waf install --prefix=/home/node/.local && \
    # Fix RPATH so libessentia.so is found without LD_LIBRARY_PATH
    ESSENTIA_SO=$(find /home/node/.local/lib -name "_essentia*.so" | head -1) && \
    if [ -n "$ESSENTIA_SO" ]; then \
      /home/node/.local/bin/patchelf --set-rpath '$ORIGIN/../../../' "$ESSENTIA_SO"; \
    fi && \
    # Cleanup
    rm -rf /tmp/essentia /tmp/eigen; \
  else \
    pip3 install --break-system-packages --no-cache-dir essentia 2>/dev/null || \
      echo "WARN: essentia install failed on $ARCH, skipping"; \
  fi

# ── xLights ──────────────────────────────────────────────────────────────────
# amd64: download + extract AppImage, run locally via Xvfb
# arm64: SSH to macOS host and run the native xLights.app binary
ARG XLIGHTS_VERSION=2026.03
USER root
RUN ARCH=$(dpkg --print-architecture) && \
  if [ "$ARCH" = "amd64" ]; then \
    wget -q "https://github.com/xLightsSequencer/xLights/releases/download/${XLIGHTS_VERSION}/xLights-${XLIGHTS_VERSION}-x86_64.AppImage" \
      -O /usr/local/bin/xLights.AppImage && \
    chmod +x /usr/local/bin/xLights.AppImage && \
    cd /opt && /usr/local/bin/xLights.AppImage --appimage-extract && \
    mv squashfs-root xlights && \
    ln -sf /opt/xlights/AppRun /usr/local/bin/xLights && \
    rm /usr/local/bin/xLights.AppImage; \
  else \
    echo "INFO: arm64 detected — xLights will run on macOS host via SSH"; \
  fi && \
  # SSH config for host.docker.internal (arm64 path)
  mkdir -p /home/node/.ssh && \
  printf 'Host host.docker.internal\n  StrictHostKeyChecking no\n  UserKnownHostsFile /dev/null\n  LogLevel ERROR\n' \
    > /home/node/.ssh/config && \
  chown -R node:node /home/node/.ssh && chmod 700 /home/node/.ssh && chmod 600 /home/node/.ssh/config
USER node

# ── xLights helper scripts ──────────────────────────────────────────────────
COPY xlights-render.sh xlights-check.sh /usr/local/bin/
USER root
RUN chmod +x /usr/local/bin/xlights-render.sh /usr/local/bin/xlights-check.sh
USER node

# Create .venv-vamp outside the workspace bind mount so it survives container restarts.
# The XLIGHT_VENV_VAMP env var (set in devcontainer.json containerEnv) points the
# subprocess runner here instead of looking inside /workspace.
RUN mkdir -p /home/node/.venv-vamp/bin && \
  ln -sf $(which python3) /home/node/.venv-vamp/bin/python

# Copy and set up firewall script
COPY init-firewall.sh /usr/local/bin/
USER root
RUN chmod +x /usr/local/bin/init-firewall.sh && \
  echo "node ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh" > /etc/sudoers.d/node-firewall && \
  chmod 0440 /etc/sudoers.d/node-firewall
USER node
