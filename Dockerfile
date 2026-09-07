# Il sito e' fatto di file statici: non c'e' niente da compilare, solo da
# servire. La build e' una copia, e dura un istante.
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY site/ /usr/share/nginx/html/
