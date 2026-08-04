FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
EXPOSE 5173
# --host binds Vite to 0.0.0.0; without it Vite only listens on the
# container's loopback interface and the published port is unreachable.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
