FROM ubuntu:focal
RUN apt-get update && apt-get install -y make python3 python3-pip vim python3-venv git
RUN DEBIAN_FRONTEND=noninteractive apt-get install -y python3-tk
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
# Download requirements separately so Docker sees it as a unique layer
ADD https://raw.githubusercontent.com/Raptacon/Robot-2025/main/requirements.txt /tmp/requirements.txt

# Install requirements into the venv
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
 && rm /tmp/requirements.txt

# Make venv auto-activate for interactive shells
RUN echo "source /opt/venv/bin/activate" >> /root/.bashrc
# Default command is interactive bash
CMD ["/bin/bash"]
