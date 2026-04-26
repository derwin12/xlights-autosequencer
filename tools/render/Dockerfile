FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb \
        ca-certificates \
        libgl1 \
        libglu1-mesa \
        libgtk-3-0 \
        libwebkit2gtk-4.1-0 \
        libsdl2-2.0-0 \
        libcurl4 \
        libsecret-1-0 \
        libnotify4 \
        libssl3 \
        libxkbcommon0 \
        libegl1 \
        libgles2 \
        mesa-utils \
        libosmesa6 \
        ffmpeg \
        file \
        squashfs-tools \
    && rm -rf /var/lib/apt/lists/*

# AppImage = ELF runtime + appended squashfs. We extract on the host (see build.sh)
# and COPY the extracted tree directly. Avoids needing fuse / Rosetta / qemu at build.
WORKDIR /opt/xlights
COPY xlights /opt/xlights/xlights
RUN chmod +x /opt/xlights/xlights/AppRun /opt/xlights/xlights/usr/bin/xlights 2>/dev/null || true

WORKDIR /work
ENV LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe
COPY render.sh /usr/local/bin/render.sh
RUN chmod +x /usr/local/bin/render.sh
ENTRYPOINT ["/usr/local/bin/render.sh"]
