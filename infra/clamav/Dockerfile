FROM clamav/clamav:stable
COPY --chown=clamav:clamav clamd.conf /etc/clamav/clamd.conf
COPY --chown=clamav:clamav freshclam.conf /etc/clamav/freshclam.conf
USER clamav
ENTRYPOINT ["clamd"]
CMD ["--foreground", "--config-file=/etc/clamav/clamd.conf"]
