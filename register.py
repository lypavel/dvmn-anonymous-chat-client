import asyncio
import logging
import tkinter as tk
from tkinter import Tk

from configargparse import Namespace

from chat_utils.authentication import register_user
from chat_utils.parse_args import parse_arguments


class TokenApp:
    def __init__(self, root: Tk, args: Namespace) -> None:
        self.host = args.host
        self.port = args.write_port

        self.root = root
        self.root.geometry('300x250')
        self.root.title('Регистрация')

        self.nickname_label = tk.Label(root, text='Никнейм:')
        self.nickname_label.pack(pady=10)

        self.nickname_entry = tk.Entry(root, width=30)
        self.nickname_entry.pack(pady=5)

        self.ok_button = tk.Button(root,
                                   text='Получить токен',
                                   command=self.on_btn_click)
        self.ok_button.pack(pady=10)

        self.token_label = tk.Label(root, text='', width=30)
        self.token_label.pack(pady=10)

        self.update_user_data()

    def on_btn_click(self):
        nickname = self.nickname_entry.get()
        # prevent creating multiple accounts
        self.ok_button.config(state='disabled')

        asyncio.run(self.generate_user_token(nickname))

    async def generate_user_token(self, entered_nickname: str) -> None:
        chat_nickname, token = await register_user(
            self.host,
            self.port,
            entered_nickname
        )

        self.update_user_data(nickname=chat_nickname,
                              token=token)

    def update_user_data(self,
                         nickname: str = '',
                         token: str = '') -> None:

        user_data = (f'Ваш никнейм:\n{nickname}\n'
                     f'Ваш токен:\n{token}')

        if nickname and token:
            user_data = '\n'.join([user_data,
                                   'Регистрационные данные сохранены в',
                                   './credentials.json'])

        self.token_label.config(text=user_data)


def main() -> None:
    logging.basicConfig(
        level=logging.DEBUG
    )

    args = parse_arguments()

    root = Tk()
    TokenApp(root, args)
    root.mainloop()


if __name__ == '__main__':
    main()
