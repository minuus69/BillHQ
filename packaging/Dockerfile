# Builds on an old Debian, because an executable only runs on systems with the
# same glibc as the build machine or newer. Debian 11 has glibc 2.31.
FROM python:3.13-slim-bullseye
RUN apt-get update && apt-get install -y --no-install-recommends \
    libzbar0 libcairo2 libgl1 libglib2.0-0 binutils
COPY requirements-build.txt /src/
RUN pip install --no-cache-dir -r /src/requirements-build.txt
COPY . /src
WORKDIR /src
RUN pyinstaller packaging/BillHQ.spec --noconfirm --distpath /out --workpath /tmp/work
RUN /out/BillHQ --self-check /tmp/check
