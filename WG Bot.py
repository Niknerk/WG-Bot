import subprocess
import os
import ipaddress
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Params
WG_CONF_PATH = '/etc/wireguard/wg0.conf'
WG_INTERFACE = 'wg0'

# Your Bot token and User ID
TOKEN = 'Bot token'
AUTHORIZED_USER_ID = User ID


def save_config(config_text):
    with open(WG_CONF_PATH, 'w') as config_file:
        config_file.write(config_text)

def read_config():
    if not os.path.exists(WG_CONF_PATH):
        return ""
    with open(WG_CONF_PATH, 'r') as config_file:
        return config_file.read()

я
def restricted(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != AUTHORIZED_USER_ID:
            await update.message.reply_text("У вас нет прав для выполнения этой команды.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


@restricted
async def list_clients(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config_text = read_config()
    clients = []
    for line in config_text.splitlines():
        if line.startswith('#'):
            clients.append(line[1:].strip())
    if clients:
        await update.message.reply_text("Список клиентов:\n" + "\n".join(clients))
    else:
        await update.message.reply_text("Клиенты не найдены.")

@restricted
async def add_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите имя нового клиента:")
    context.user_data['action'] = 'add_client'

@restricted
async def remove_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите имя клиента для удаления:")
    context.user_data['action'] = 'remove_client'

@restricted
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.user_data.get('action')
    if not action:
        return

    if action == 'add_client':
        client_name = update.message.text.strip()
        private_key = subprocess.run(['wg', 'genkey'], capture_output=True, text=True).stdout.strip()
        public_key = subprocess.run(['wg', 'pubkey'], input=private_key, capture_output=True, text=True).stdout.strip()

        config_text = read_config()
        used_ips = set()
        for line in config_text.splitlines():
            if line.strip().startswith('AllowedIPs'):
                ip = line.split('=')[1].strip().split('/')[0]
                used_ips.add(ip)

        network = ipaddress.IPv4Network('10.0.0.0/24')
        client_ip = None
        for ip in network.hosts():
            if str(ip) not in used_ips:
                client_ip = str(ip)
                break

        if not client_ip:
            await update.message.reply_text("Не удалось найти свободный IP-адрес.")
            return

        peer_entry = f"\n# {client_name}\n[Peer]\nPublicKey = {public_key}\nAllowedIPs = {client_ip}/32\n"

        config_text += peer_entry
        save_config(config_text)

        client_config = f"""
[Interface]
PrivateKey = {private_key}
Address = {client_ip}/24
DNS = 8.8.8.8

[Peer]
PublicKey = Your Server Public Key
Endpoint = YourServerIP:ServerPort
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
"""
        await update.message.reply_text(f"Клиент '{client_name}' добавлен.\nIP-адрес: {client_ip}\nПриватный ключ: {private_key}\nПубличный ключ: {public_key}")
        await update.message.reply_document(document=client_config.encode(), filename=f'{client_name}_wg0.conf')

    elif action == 'remove_client':
        client_name = update.message.text.strip()
        config_text = read_config()
        lines = config_text.splitlines()
        new_lines = []
        skip = False
        for line in lines:
            if line.startswith(f'# {client_name}'):
                skip = True
                continue
            if skip and line.startswith('[Peer]'):
                skip = False
                continue
            if not skip:
                new_lines.append(line)
        if len(new_lines) == len(lines):
            await update.message.reply_text(f"Клиент '{client_name}' не найден.")
        else:
            save_config("\n".join(new_lines))
            await update.message.reply_text(f"Клиент '{client_name}' удален.")

    context.user_data['action'] = None

@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = ReplyKeyboardMarkup([['Users', 'Add Client', 'Remove Client']], one_time_keyboard=True)
    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^(Users)$"), list_clients))
    app.add_handler(MessageHandler(filters.Regex("^(Add Client)$"), add_client))
    app.add_handler(MessageHandler(filters.Regex("^(Remove Client)$"), remove_client))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()

if __name__ == '__main__':
    main()
