FROM almalinux:9

ARG TIMESTAMP_IMAGE=gratia-probe-k8s:release-$(date +%Y%m%d-%H%M)
ENV GRATIA_PROBE_VERSION=$TIMESTAMP_IMAGE

# Install EPEL, the OSG software base repo, and gratia-probe-common
RUN yum install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm && \
    yum install -y https://repo.opensciencegrid.org/osg/23-main/osg-23-main-el9-release-latest.rpm && \
    yum install -y gratia-probe-common python3-pip

# Make probe runnable as non-root
RUN chmod 777 /var/lock/gratia /var/lib/gratia/data /var/lib/gratia/tmp /var/log/gratia
WORKDIR /gratia
COPY requirements.txt /gratia
RUN pip install -r requirements.txt
COPY ProbeConfig /etc/gratia/kubernetes/
COPY *.py /gratia/

CMD python3 kubernetes_meter.py
