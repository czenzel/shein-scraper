FROM ubuntu:latest

# Create Application Directory
RUN mkdir /app
WORKDIR /app

# Update package lists and packages on system
RUN apt-get -y update
RUN apt-get -y dist-upgrade

# Install essential python, pip, and build requirements
RUN apt-get install -y python3 python3-pip build-essential git wget

# Install Google Chrome
RUN wget -q "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb"
RUN apt-get install -y "./google-chrome-stable_current_amd64.deb"
RUN rm -f "google-chrome-stable_current_amd64.deb"

# Install Google Chrome - ChromeDriver
RUN apt-get install -y unzip
RUN wget -q "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/120.0.6099.109/linux64/chromedriver-linux64.zip"
RUN unzip "chromedriver-linux64.zip"
RUN cp "chromedriver-linux64/chromedriver" "/usr/bin"
RUN rm -rf "chromedriver-linux64"
RUN rm -f "chromedriver-linux64.zip"

# Copy the application files to the machine
COPY requirements.txt requirements.txt

# Restore package requirements
RUN pip3 install -r requirements.txt

# Copy the files to the machine
COPY . .

# Run the provided script to retrive product information
# Commented out for future project(s)
# CMD ["./run.sh"]

CMD ["bash"]