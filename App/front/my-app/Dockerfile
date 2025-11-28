# Stage 1: Build the React App
FROM node:18-alpine as build

WORKDIR /app

# Copy package info and install dependencies
COPY package*.json ./
RUN npm install

# Copy source code
COPY . .

# Build the app (Creates the /dist folder)
# We default to localhost for development, but you can override this later
ARG VITE_API_BASE_URL="http://127.0.0.1:8000"
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# Stage 2: Serve with Nginx
FROM nginx:alpine

# Copy the built files from Stage 1 into Nginx
COPY --from=build /app/dist /usr/share/nginx/html

# Expose port 80 (Standard Web Port)
EXPOSE 80

# Start Nginx
CMD ["nginx", "-g", "daemon off;"]