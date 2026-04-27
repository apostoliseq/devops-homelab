# Single stage — no build step needed, just copy static files into Nginx.
FROM nginx:1.27-alpine

# Remove the default Nginx config and replace with ours
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy the static HTML file into the directory Nginx serves by default
COPY static/ /usr/share/nginx/html/

# Nginx runs as root by default to bind port 80, but worker processes
# drop to the built-in 'nginx' user automatically.
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
