def get_details():
        info = {}
        for line in open('config'):
            if '=' in line:
                key, value = line.split('=')
                info[key.strip()] = value.strip()
        return info
