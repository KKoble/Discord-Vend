import discord
from discord.ext import commands
from discord import ui, app_commands
import aiosqlite
import os

from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv("TOKEN")
DB_DIR = "db"

EMOJI_NOTICE  = discord.PartialEmoji(name="Announce", id=1499680233127809124)
EMOJI_PRODUCT = discord.PartialEmoji(name="Product",  id=1499680158377050283)
EMOJI_BUY     = discord.PartialEmoji(name="Buy",      id=1499680201565798470)
EMOJI_CHARGE  = discord.PartialEmoji(name="Charge",   id=1499680357023223989)
EMOJI_ME      = discord.PartialEmoji(name="Info",     id=1499680088097034311)

LOGO_URL = "https://i.pinimg.com/originals/13/8d/52/138d52a8f429510e2c16bd67990dae3c.jpg"

os.makedirs(DB_DIR, exist_ok=True)

def db_path(guild_id: int) -> str:
    return f"{DB_DIR}/{guild_id}.db"

async def init_db(guild_id: int):
    async with aiosqlite.connect(db_path(guild_id)) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                balance     INTEGER DEFAULT 0,
                total_spent INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS notices (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                title   TEXT,
                content TEXT
            );
            CREATE TABLE IF NOT EXISTS categories (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE
            );
            CREATE TABLE IF NOT EXISTS products (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT,
                price       INTEGER,
                category_id INTEGER,
                FOREIGN KEY(category_id) REFERENCES categories(id)
            );
            CREATE TABLE IF NOT EXISTS stocks (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                content    TEXT,
                FOREIGN KEY(product_id) REFERENCES products(id)
            );
            CREATE TABLE IF NOT EXISTS log_channels (
                type       TEXT PRIMARY KEY,
                channel_id INTEGER
            );
            CREATE TABLE IF NOT EXISTS vending_config (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS server_config (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        await db.commit()

async def ensure_user(guild_id: int, user: discord.Member):
    async with aiosqlite.connect(db_path(guild_id)) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (user.id, user.display_name)
        )
        await db.execute(
            "UPDATE users SET username = ? WHERE user_id = ?",
            (user.display_name, user.id)
        )
        await db.commit()

async def get_user(guild_id: int, user_id: int):
    async with aiosqlite.connect(db_path(guild_id)) as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            return await cur.fetchone()

async def get_notices(guild_id: int):
    async with aiosqlite.connect(db_path(guild_id)) as db:
        async with db.execute("SELECT * FROM notices ORDER BY id DESC") as cur:
            return await cur.fetchall()

async def get_categories(guild_id: int):
    async with aiosqlite.connect(db_path(guild_id)) as db:
        async with db.execute("SELECT * FROM categories") as cur:
            return await cur.fetchall()

async def get_products_by_category(guild_id: int, category_id: int):
    async with aiosqlite.connect(db_path(guild_id)) as db:
        async with db.execute(
            "SELECT p.id, p.name, p.price, COUNT(s.id) as stock "
            "FROM products p LEFT JOIN stocks s ON s.product_id = p.id "
            "WHERE p.category_id = ? GROUP BY p.id", (category_id,)
        ) as cur:
            return await cur.fetchall()

async def get_log_channel(guild_id: int, log_type: str):
    async with aiosqlite.connect(db_path(guild_id)) as db:
        async with db.execute("SELECT channel_id FROM log_channels WHERE type = ?", (log_type,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else None

class VendingView(ui.LayoutView):
    def __init__(self, title: str, desc: str, img_url: str):
        super().__init__(timeout=None)

        btn_notice  = ui.Button(label="공지",   emoji=EMOJI_NOTICE,  style=discord.ButtonStyle.secondary)
        btn_product = ui.Button(label="상품",   emoji=EMOJI_PRODUCT, style=discord.ButtonStyle.secondary)
        btn_buy     = ui.Button(label="구매",   emoji=EMOJI_BUY,     style=discord.ButtonStyle.secondary)
        btn_charge  = ui.Button(label="충전",   emoji=EMOJI_CHARGE,  style=discord.ButtonStyle.secondary)
        btn_me      = ui.Button(label="내정보", emoji=EMOJI_ME,      style=discord.ButtonStyle.secondary)

        btn_notice.callback  = self.on_notice
        btn_product.callback = self.on_product
        btn_buy.callback     = self.on_buy
        btn_charge.callback  = self.on_charge
        btn_me.callback      = self.on_me

        gallery = ui.MediaGallery()
        gallery.add_item(media=img_url)

        self.add_item(ui.Container(
            ui.TextDisplay(f"# {title}"),
            ui.Separator(),
            ui.TextDisplay(desc),
            gallery,
            ui.Separator(),
            ui.ActionRow(btn_notice, btn_product, btn_buy, btn_charge, btn_me),
            accent_color=discord.Color.blurple()
        ))

    async def on_notice(self, interaction: discord.Interaction):
        await ensure_user(interaction.guild.id, interaction.user)
        notices = await get_notices(interaction.guild.id)
        text = notices[0][2] if notices else "등록된 공지사항이 없습니다."
        view = ui.LayoutView(timeout=60)
        view.add_item(ui.Container(
            ui.TextDisplay("# 공지사항"),
            ui.Separator(),
            ui.TextDisplay(text),
            ui.Separator(),
            accent_color=discord.Color.blurple()
        ))
        await interaction.response.send_message(view=view, ephemeral=True)

    async def on_product(self, interaction: discord.Interaction):
        await ensure_user(interaction.guild.id, interaction.user)
        cats = await get_categories(interaction.guild.id)
        await interaction.response.send_message(
            view=ProductView(interaction.guild.id, cats),
            ephemeral=True
        )

    async def on_buy(self, interaction: discord.Interaction):
        await ensure_user(interaction.guild.id, interaction.user)
        cats = await get_categories(interaction.guild.id)
        await interaction.response.send_message(
            view=BuyView(interaction.guild.id, interaction.user, cats),
            ephemeral=True
        )

    async def on_charge(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ChargeModal(interaction.guild.id, interaction.user))

    async def on_me(self, interaction: discord.Interaction):
        await ensure_user(interaction.guild.id, interaction.user)
        row = await get_user(interaction.guild.id, interaction.user.id)
        balance     = f"{row[2]:,}원" if row else "0원"
        total_spent = f"{row[3]:,}원" if row else "0원"
        nickname    = interaction.user.display_name

        view = ui.LayoutView(timeout=60)
        view.add_item(ui.Container(
            ui.TextDisplay("# 내 정보"),
            ui.Separator(),
            ui.TextDisplay(f"닉네임 — {nickname}\n잔액 — {balance}\n총 구매액 — {total_spent}"),
            ui.Separator(),
            accent_color=discord.Color.blurple()
        ))
        await interaction.response.send_message(view=view, ephemeral=True)

class ProductView(ui.LayoutView):
    def __init__(self, guild_id: int, cats: list):
        super().__init__(timeout=120)
        self.guild_id = guild_id

        options = [discord.SelectOption(label=c[1], value=str(c[0])) for c in cats] if cats else [
            discord.SelectOption(label="카테고리 없음", value="none")
        ]
        dropdown = ui.Select(placeholder="카테고리를 선택하세요...", options=options)
        dropdown.callback = self.on_select

        self.add_item(ui.Container(
            ui.TextDisplay("# 제품 목록"),
            ui.Separator(),
            ui.TextDisplay("카테고리를 선택하면 제품 목록이 표시됩니다."),
            ui.Separator(),
            ui.ActionRow(dropdown),
            accent_color=discord.Color.blurple()
        ))

    async def on_select(self, interaction: discord.Interaction):
        cat_id = interaction.data["values"][0]
        if cat_id == "none":
            await interaction.response.defer()
            return
        products = await get_products_by_category(self.guild_id, int(cat_id))
        if products:
            lines = "\n".join(f"* {p[1]} | `{p[2]:,}원` | 재고: `{p[3]}개`" for p in products)
        else:
            lines = "등록된 제품이 없습니다."

        cats = await get_categories(self.guild_id)
        options = [discord.SelectOption(label=c[1], value=str(c[0])) for c in cats]
        dropdown = ui.Select(placeholder="카테고리를 선택하세요...", options=options)
        dropdown.callback = self.on_select

        self.clear_items()
        self.add_item(ui.Container(
            ui.TextDisplay("# 제품 목록"),
            ui.Separator(),
            ui.TextDisplay(lines),
            ui.Separator(),
            ui.ActionRow(dropdown),
            accent_color=discord.Color.blurple()
        ))
        await interaction.response.edit_message(view=self)

class BuyView(ui.LayoutView):
    def __init__(self, guild_id: int, user: discord.Member, cats: list, selected_cat=None, selected_product=None):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.user = user
        self.selected_cat = selected_cat
        self.selected_product = selected_product
        self._build(cats)

    def _build(self, cats):
        self.clear_items()
        cat_options = [discord.SelectOption(label=c[1], value=str(c[0])) for c in cats] if cats else [
            discord.SelectOption(label="카테고리 없음", value="none")
        ]
        cat_dropdown = ui.Select(placeholder="카테고리를 선택하세요...", options=cat_options)
        cat_dropdown.callback = self.on_cat_select

        rows = [ui.ActionRow(cat_dropdown)]

        if self.selected_product:
            buy_btn = ui.Button(label="구매하기", style=discord.ButtonStyle.success)
            buy_btn.callback = self.on_buy
            rows.append(ui.ActionRow(buy_btn))

        self.add_item(ui.Container(
            ui.TextDisplay("# 구매"),
            ui.Separator(),
            ui.TextDisplay("카테고리와 제품을 선택하세요."),
            ui.Separator(),
            *rows,
            accent_color=discord.Color.green()
        ))

    async def on_cat_select(self, interaction: discord.Interaction):
        cat_id = interaction.data["values"][0]
        if cat_id == "none":
            await interaction.response.defer()
            return
        self.selected_cat = int(cat_id)
        products = await get_products_by_category(self.guild_id, self.selected_cat)

        self.clear_items()

        if products:
            prod_options = [discord.SelectOption(label=f"{p[1]} ({p[2]:,}원) | 재고 {p[3]}개", value=f"{p[0]}|{p[1]}|{p[2]}") for p in products if p[3] > 0]
        else:
            prod_options = []

        if prod_options:
            prod_dropdown = ui.Select(placeholder="제품을 선택하세요...", options=prod_options)
            prod_dropdown.callback = self.on_prod_select
            self.add_item(ui.Container(
                ui.TextDisplay("# 구매"),
                ui.Separator(),
                ui.TextDisplay("제품을 선택하세요."),
                ui.Separator(),
                ui.ActionRow(prod_dropdown),
                accent_color=discord.Color.green()
            ))
        else:
            self.add_item(ui.Container(
                ui.TextDisplay("# 구매"),
                ui.Separator(),
                ui.TextDisplay("재고가 있는 제품이 없습니다."),
                ui.Separator(),
                accent_color=discord.Color.red()
            ))
        await interaction.response.edit_message(view=self)

    async def on_prod_select(self, interaction: discord.Interaction):
        val = interaction.data["values"][0].split("|")
        self.selected_product = {"id": int(val[0]), "name": val[1], "price": int(val[2])}
        await interaction.response.send_modal(BuyModal(self.guild_id, self.user, self.selected_product))

    async def on_buy(self, interaction: discord.Interaction):
        await interaction.response.send_modal(BuyModal(self.guild_id, self.user, self.selected_product))

class BuyModal(ui.Modal, title="구매"):
    quantity = ui.TextInput(label="수량", placeholder="1", min_length=1, max_length=3)

    def __init__(self, guild_id, user, product):
        super().__init__()
        self.guild_id = guild_id
        self.user = user
        self.product = product

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qty = int(self.quantity.value)
            if qty < 1:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("올바른 수량을 입력하세요.", ephemeral=True)
            return

        total = self.product["price"] * qty
        row = await get_user(self.guild_id, self.user.id)
        balance = row[2] if row else 0

        if balance < total:
            await interaction.response.send_message(
                f"잔액이 부족합니다. (잔액: {balance:,}원 / 필요: {total:,}원)", ephemeral=True
            )
            return

        async with aiosqlite.connect(db_path(self.guild_id)) as db:
            async with db.execute(
                "SELECT id, content FROM stocks WHERE product_id = ? LIMIT ?",
                (self.product["id"], qty)
            ) as cur:
                stocks = await cur.fetchall()

            if len(stocks) < qty:
                await interaction.response.send_message("재고가 부족합니다.", ephemeral=True)
                return

            stock_ids = [s[0] for s in stocks]
            contents  = [s[1] for s in stocks]

            await db.execute(
                f"DELETE FROM stocks WHERE id IN ({','.join('?'*len(stock_ids))})", stock_ids
            )
            await db.execute(
                "UPDATE users SET balance = balance - ?, total_spent = total_spent + ? WHERE user_id = ?",
                (total, total, self.user.id)
            )
            await db.commit()

        receipt = "\n".join(contents)
        try:
            dm_view = ui.LayoutView(timeout=None)
            dm_view.add_item(ui.Container(
                ui.TextDisplay("# 구매 완료"),
                ui.Separator(),
                ui.TextDisplay(f"제품: {self.product['name']}"),
                ui.Separator(),
                ui.TextDisplay(f"수령 내용:\n{receipt}"),
                ui.Separator(),
                accent_color=discord.Color.green()
            ))
            await self.user.send(view=dm_view)
        except discord.Forbidden:
            pass

        await interaction.response.send_message(
            f"✅ 구매 완료! DM을 확인하세요. (차감: {total:,}원)", ephemeral=True
        )

        log_ch_id = await get_log_channel(self.guild_id, "구매")
        if log_ch_id:
            ch = interaction.guild.get_channel(log_ch_id)
            if ch:
                await ch.send(
                    embed=discord.Embed(
                        title="구매 로그",
                        description=f"{self.user.mention} | {self.product['name']} x{qty} | {total:,}원",
                        color=discord.Color.green()
                    )
                )

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

def admin_check():
    async def predicate(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("관리자 전용 명령어입니다.", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

@bot.tree.command(name="공지사항_등록", description="공지사항을 등록합니다.")
@admin_check()
async def notice_add(interaction: discord.Interaction):
    await interaction.response.send_modal(NoticeModal(interaction.guild.id, mode="add"))

@bot.tree.command(name="공지사항_수정", description="공지사항을 수정합니다.")
@admin_check()
async def notice_edit(interaction: discord.Interaction):
    await interaction.response.send_modal(NoticeModal(interaction.guild.id, mode="edit"))

@bot.tree.command(name="공지사항_삭제", description="공지사항을 삭제합니다.")
@admin_check()
async def notice_delete(interaction: discord.Interaction):
    async with aiosqlite.connect(db_path(interaction.guild.id)) as db:
        await db.execute("DELETE FROM notices WHERE id = (SELECT id FROM notices ORDER BY id DESC LIMIT 1)")
        await db.commit()
    await interaction.response.send_message("최근 공지사항이 삭제되었습니다.", ephemeral=True)

class NoticeModal(ui.Modal, title="공지사항"):
    notice_content = ui.TextInput(label="내용", style=discord.TextStyle.paragraph, max_length=2000)

    def __init__(self, guild_id, mode):
        super().__init__()
        self.guild_id = guild_id
        self.mode = mode

    async def on_submit(self, interaction: discord.Interaction):
        async with aiosqlite.connect(db_path(self.guild_id)) as db:
            if self.mode == "add":
                await db.execute("INSERT INTO notices (title, content) VALUES (?, ?)",
                                 ("공지사항", self.notice_content.value))
            else:
                await db.execute(
                    "UPDATE notices SET content = ? WHERE id = (SELECT id FROM notices ORDER BY id DESC LIMIT 1)",
                    (self.notice_content.value,)
                )
            await db.commit()
        await interaction.response.send_message("공지사항이 저장되었습니다.", ephemeral=True)

@bot.tree.command(name="카테고리_생성", description="카테고리를 생성합니다.")
@admin_check()
async def cat_create(interaction: discord.Interaction):
    await interaction.response.send_modal(CategoryAddModal(interaction.guild.id))

@bot.tree.command(name="카테고리_수정", description="카테고리를 수정합니다.")
@admin_check()
async def cat_edit(interaction: discord.Interaction):
    await interaction.response.send_modal(CategoryEditModal(interaction.guild.id))

@bot.tree.command(name="카테고리_삭제", description="카테고리를 삭제합니다.")
@admin_check()
async def cat_delete(interaction: discord.Interaction):
    await interaction.response.send_modal(CategoryDeleteModal(interaction.guild.id))

class CategoryAddModal(ui.Modal, title="카테고리 생성"):
    name = ui.TextInput(label="카테고리 이름", max_length=50)

    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        async with aiosqlite.connect(db_path(self.guild_id)) as db:
            await db.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (self.name.value,))
            await db.commit()
        await interaction.response.send_message("카테고리가 생성되었습니다.", ephemeral=True)

class CategoryEditModal(ui.Modal, title="카테고리 수정"):
    old_name = ui.TextInput(label="기존 카테고리 이름")
    new_name = ui.TextInput(label="새 카테고리 이름", max_length=50)

    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        async with aiosqlite.connect(db_path(self.guild_id)) as db:
            await db.execute("UPDATE categories SET name = ? WHERE name = ?",
                             (self.new_name.value, self.old_name.value))
            await db.commit()
        await interaction.response.send_message("카테고리가 수정되었습니다.", ephemeral=True)

class CategoryDeleteModal(ui.Modal, title="카테고리 삭제"):
    name = ui.TextInput(label="삭제할 카테고리 이름")

    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        async with aiosqlite.connect(db_path(self.guild_id)) as db:
            await db.execute("DELETE FROM categories WHERE name = ?", (self.name.value,))
            await db.commit()
        await interaction.response.send_message("카테고리가 삭제되었습니다.", ephemeral=True)

@bot.tree.command(name="제품_등록", description="제품을 등록합니다.")
@admin_check()
async def product_add(interaction: discord.Interaction):
    await interaction.response.send_modal(ProductAddModal(interaction.guild.id))

@bot.tree.command(name="제품_수정", description="제품을 수정합니다.")
@admin_check()
async def product_edit(interaction: discord.Interaction):
    await interaction.response.send_modal(ProductEditModal(interaction.guild.id))

@bot.tree.command(name="제품_삭제", description="제품을 삭제합니다.")
@admin_check()
async def product_delete(interaction: discord.Interaction):
    await interaction.response.send_modal(ProductDeleteModal(interaction.guild.id))

class ProductAddModal(ui.Modal, title="제품 등록"):
    name  = ui.TextInput(label="제품 이름", max_length=100)
    price = ui.TextInput(label="가격 (숫자만)", max_length=10)

    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price = int(self.price.value)
        except ValueError:
            await interaction.response.send_message("가격은 숫자만 입력하세요.", ephemeral=True)
            return

        cats = await get_categories(self.guild_id)
        if not cats:
            await interaction.response.send_message("먼저 카테고리를 생성하세요.", ephemeral=True)
            return

        options = [discord.SelectOption(label=c[1], value=str(c[0])) for c in cats]
        dropdown = ui.Select(placeholder="카테고리를 선택하세요...", options=options)

        async def on_select(inter: discord.Interaction):
            cat_id = int(inter.data["values"][0])
            async with aiosqlite.connect(db_path(self.guild_id)) as db:
                await db.execute("INSERT INTO products (name, price, category_id) VALUES (?, ?, ?)",
                                 (self.name.value, price, cat_id))
                await db.commit()
            await inter.response.defer()
            await inter.edit_original_response(content=f"✅ 제품 **{self.name.value}** 등록 완료!", view=None)

        dropdown.callback = on_select

        view = ui.LayoutView(timeout=60)
        view.add_item(ui.Container(
            ui.TextDisplay(f"**{self.name.value}** ({price:,}원) — 카테고리를 선택하세요."),
            ui.ActionRow(dropdown),
            accent_color=discord.Color.blurple()
        ))
        await interaction.response.send_message(view=view, ephemeral=True)

class ProductEditModal(ui.Modal, title="제품 수정"):
    name      = ui.TextInput(label="수정할 제품 이름")
    new_name  = ui.TextInput(label="새 이름 (변경 없으면 비워두세요)", required=False)
    new_price = ui.TextInput(label="새 가격 (변경 없으면 비워두세요)", required=False)

    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        async with aiosqlite.connect(db_path(self.guild_id)) as db:
            async with db.execute("SELECT id FROM products WHERE name = ?", (self.name.value,)) as cur:
                row = await cur.fetchone()
            if not row:
                await interaction.response.send_message("제품을 찾을 수 없습니다.", ephemeral=True)
                return
            product_id = row[0]
            if self.new_name.value:
                await db.execute("UPDATE products SET name = ? WHERE id = ?", (self.new_name.value, product_id))
            if self.new_price.value:
                try:
                    await db.execute("UPDATE products SET price = ? WHERE id = ?", (int(self.new_price.value), product_id))
                except ValueError:
                    pass
            await db.commit()

        cats = await get_categories(self.guild_id)
        options = [discord.SelectOption(label=c[1], value=str(c[0])) for c in cats]
        options.insert(0, discord.SelectOption(label="카테고리 변경 안 함", value="skip"))
        dropdown = ui.Select(placeholder="카테고리를 변경하시겠습니까?", options=options)

        async def on_select(inter: discord.Interaction):
            val = inter.data["values"][0]
            if val != "skip":
                async with aiosqlite.connect(db_path(self.guild_id)) as db:
                    await db.execute("UPDATE products SET category_id = ? WHERE id = ?", (int(val), product_id))
                    await db.commit()
            await inter.response.edit_message(content="제품이 수정되었습니다.", view=None)

        dropdown.callback = on_select

        view = ui.LayoutView(timeout=60)
        view.add_item(ui.Container(
            ui.TextDisplay("카테고리를 변경하시겠습니까?"),
            ui.ActionRow(dropdown),
            accent_color=discord.Color.blurple()
        ))
        await interaction.response.send_message(view=view, ephemeral=True)

class ProductDeleteModal(ui.Modal, title="제품 삭제"):
    name = ui.TextInput(label="삭제할 제품 이름")

    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        async with aiosqlite.connect(db_path(self.guild_id)) as db:
            await db.execute("DELETE FROM products WHERE name = ?", (self.name.value,))
            await db.commit()
        await interaction.response.send_message("제품이 삭제되었습니다.", ephemeral=True)

@bot.tree.command(name="재고_추가", description="재고를 추가합니다.")
@admin_check()
async def stock_add(interaction: discord.Interaction):
    cats = await get_categories(interaction.guild.id)
    if not cats:
        await interaction.response.send_message("카테고리가 없습니다.", ephemeral=True)
        return
    view = StockSelectView(interaction.guild.id, mode="add", cats=cats)
    await interaction.response.send_message(view=view, ephemeral=True)

@bot.tree.command(name="재고_삭제", description="재고를 삭제합니다.")
@admin_check()
async def stock_delete(interaction: discord.Interaction):
    cats = await get_categories(interaction.guild.id)
    if not cats:
        await interaction.response.send_message("카테고리가 없습니다.", ephemeral=True)
        return
    view = StockSelectView(interaction.guild.id, mode="delete", cats=cats)
    await interaction.response.send_message(view=view, ephemeral=True)

class StockSelectView(ui.LayoutView):
    def __init__(self, guild_id, mode, cats):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.mode = mode

        options = [discord.SelectOption(label=c[1], value=str(c[0])) for c in cats]
        dropdown = ui.Select(placeholder="카테고리를 선택하세요...", options=options)
        dropdown.callback = self.on_cat_select

        self.add_item(ui.Container(
            ui.TextDisplay("**카테고리를 선택하세요**"),
            ui.ActionRow(dropdown),
            accent_color=discord.Color.orange()
        ))

    async def on_cat_select(self, interaction: discord.Interaction):
        cat_id = int(interaction.data["values"][0])
        products = await get_products_by_category(self.guild_id, cat_id)
        if not products:
            await interaction.response.send_message("해당 카테고리에 제품이 없습니다.", ephemeral=True)
            return

        options = [discord.SelectOption(label=p[1], value=str(p[0])) for p in products]
        dropdown = ui.Select(placeholder="제품을 선택하세요...", options=options)
        dropdown.callback = self.make_prod_callback()

        self.clear_items()
        self.add_item(ui.Container(
            ui.TextDisplay("**제품을 선택하세요**"),
            ui.ActionRow(dropdown),
            accent_color=discord.Color.orange()
        ))
        await interaction.response.edit_message(view=self)

    def make_prod_callback(self):
        async def on_prod_select(interaction: discord.Interaction):
            product_id = int(interaction.data["values"][0])
            if self.mode == "add":
                await interaction.response.send_modal(StockAddModal(self.guild_id, product_id))
            else:
                await interaction.response.send_modal(StockDeleteModal(self.guild_id, product_id))
        return on_prod_select

class StockAddModal(ui.Modal, title="재고 추가"):
    contents = ui.TextInput(label="재고 내용 (줄바꿈으로 여러 개)", style=discord.TextStyle.paragraph)

    def __init__(self, guild_id, product_id):
        super().__init__()
        self.guild_id = guild_id
        self.product_id = product_id

    async def on_submit(self, interaction: discord.Interaction):
        lines = [l.strip() for l in self.contents.value.splitlines() if l.strip()]
        async with aiosqlite.connect(db_path(self.guild_id)) as db:
            await db.executemany(
                "INSERT INTO stocks (product_id, content) VALUES (?, ?)",
                [(self.product_id, l) for l in lines]
            )
            await db.commit()
        await interaction.response.send_message(f"재고 {len(lines)}개가 추가되었습니다.", ephemeral=True)

class StockDeleteModal(ui.Modal, title="재고 삭제"):
    content = ui.TextInput(label="삭제할 재고 내용")

    def __init__(self, guild_id, product_id):
        super().__init__()
        self.guild_id = guild_id
        self.product_id = product_id

    async def on_submit(self, interaction: discord.Interaction):
        async with aiosqlite.connect(db_path(self.guild_id)) as db:
            await db.execute(
                "DELETE FROM stocks WHERE product_id = ? AND content = ?",
                (self.product_id, self.content.value)
            )
            await db.commit()
        await interaction.response.send_message("재고가 삭제되었습니다.", ephemeral=True)

@bot.tree.command(name="충전", description="사용자 잔액을 충전합니다.")
@admin_check()
@app_commands.describe(user="충전할 사용자", amount="충전 금액")
async def charge_cmd(interaction: discord.Interaction, user: discord.Member, amount: int):
    await ensure_user(interaction.guild.id, user)
    async with aiosqlite.connect(db_path(interaction.guild.id)) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user.id))
        await db.commit()
    await interaction.response.send_message(f"{user.mention}에게 {amount:,}원이 충전되었습니다.", ephemeral=True)

    log_ch_id = await get_log_channel(interaction.guild.id, "충전")
    if log_ch_id:
        ch = interaction.guild.get_channel(log_ch_id)
        if ch:
            await ch.send(embed=discord.Embed(
                title="충전 로그",
                description=f"{user.mention} | +{amount:,}원 | 충전자: {interaction.user.mention}",
                color=discord.Color.blurple()
            ))

@bot.tree.command(name="로그채널_설정", description="로그 채널을 설정합니다.")
@admin_check()
@app_commands.describe(log_type="로그 종류", channel="채널")
@app_commands.choices(log_type=[
    app_commands.Choice(name="구매로그", value="구매"),
    app_commands.Choice(name="충전로그", value="충전"),
    app_commands.Choice(name="충전확인로그", value="충전확인"),
])
async def log_channel_set(interaction: discord.Interaction, log_type: str, channel: discord.TextChannel):
    async with aiosqlite.connect(db_path(interaction.guild.id)) as db:
        await db.execute(
            "INSERT OR REPLACE INTO log_channels (type, channel_id) VALUES (?, ?)",
            (log_type, channel.id)
        )
        await db.commit()
    await interaction.response.send_message(f"{log_type} 채널이 {channel.mention}으로 설정되었습니다.", ephemeral=True)

@bot.tree.command(name="자판기", description="자판기 메뉴를 엽니다.")
async def vending(interaction: discord.Interaction):
    await ensure_user(interaction.guild.id, interaction.user)
    async with aiosqlite.connect(db_path(interaction.guild.id)) as db:
        async with db.execute("SELECT key, value FROM vending_config") as cur:
            rows = await cur.fetchall()
    cfg     = {r[0]: r[1] for r in rows}
    title   = cfg.get("title",   interaction.guild.name)
    desc    = cfg.get("desc",    "원하시는 버튼을 클릭해주세요.")
    img_url = cfg.get("img_url", LOGO_URL)
    await interaction.response.send_message(view=VendingView(title, desc, img_url))

@bot.event
async def on_ready():
    for guild in bot.guilds:
        await init_db(guild.id)
        bot.tree.clear_commands(guild=guild)
        await bot.tree.sync(guild=guild)
    synced = await bot.tree.sync()
    print(f"로그인됨: {bot.user}")
    print(f"전역 명령어 {len(synced)}개 동기화됨")

@bot.event
async def on_guild_join(guild: discord.Guild):
    await init_db(guild.id)

@bot.tree.command(name="자판기_수정", description="자판기 메인 화면을 수정합니다.")
@admin_check()
async def vending_edit(interaction: discord.Interaction):
    async with aiosqlite.connect(db_path(interaction.guild.id)) as db:
        async with db.execute("SELECT key, value FROM vending_config") as cur:
            rows = await cur.fetchall()
    cfg = {r[0]: r[1] for r in rows}
    title   = cfg.get("title",   interaction.guild.name)
    desc    = cfg.get("desc",    "원하시는 버튼을 클릭해주세요.")
    img_url = cfg.get("img_url", LOGO_URL)

    preview_view = ui.LayoutView(timeout=None)
    gallery = ui.MediaGallery()
    gallery.add_item(media=img_url)
    preview_view.add_item(ui.Container(
        ui.TextDisplay(f"# {title}"),
        ui.Separator(),
        ui.TextDisplay(desc),
        gallery,
        accent_color=discord.Color.blurple()
    ))

    edit_view = VendingEditView(interaction.guild.id, title, desc, img_url)

    await interaction.response.send_message(view=preview_view, ephemeral=True)
    await interaction.followup.send(view=edit_view, ephemeral=True)

class VendingEditView(ui.LayoutView):
    def __init__(self, guild_id: int, title: str, desc: str, img_url: str):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.title   = title
        self.desc    = desc
        self.img_url = img_url
        self._render()

    def _render(self):
        self.clear_items()

        btn_title  = ui.Button(label="제목 수정",  style=discord.ButtonStyle.secondary)
        btn_desc   = ui.Button(label="내용 수정",  style=discord.ButtonStyle.secondary)
        btn_img    = ui.Button(label="사진 수정",  style=discord.ButtonStyle.secondary)
        btn_save   = ui.Button(label="저장",       style=discord.ButtonStyle.success)
        btn_cancel = ui.Button(label="취소",       style=discord.ButtonStyle.danger)

        btn_title.callback  = self.on_title
        btn_desc.callback   = self.on_desc
        btn_img.callback    = self.on_img
        btn_save.callback   = self.on_save
        btn_cancel.callback = self.on_cancel

        self.add_item(ui.Container(
            ui.TextDisplay("# 자판기 수정"),
            ui.Separator(),
            ui.TextDisplay(f"제목: **{self.title}**\n내용: {self.desc}\n사진: {self.img_url}"),
            ui.Separator(),
            ui.ActionRow(btn_title, btn_desc, btn_img),
            ui.ActionRow(btn_save, btn_cancel),
            accent_color=discord.Color.yellow()
        ))

    async def on_title(self, interaction: discord.Interaction):
        await interaction.response.send_modal(VendingEditModal("제목", self))

    async def on_desc(self, interaction: discord.Interaction):
        await interaction.response.send_modal(VendingEditModal("내용", self))

    async def on_img(self, interaction: discord.Interaction):
        await interaction.response.send_modal(VendingEditModal("사진", self))

    async def on_save(self, interaction: discord.Interaction):
        async with aiosqlite.connect(db_path(self.guild_id)) as db:
            await db.execute("INSERT OR REPLACE INTO vending_config (key, value) VALUES (?, ?)", ("title",   self.title))
            await db.execute("INSERT OR REPLACE INTO vending_config (key, value) VALUES (?, ?)", ("desc",    self.desc))
            await db.execute("INSERT OR REPLACE INTO vending_config (key, value) VALUES (?, ?)", ("img_url", self.img_url))
            await db.commit()
        self.clear_items()
        self.add_item(ui.Container(
            ui.TextDisplay("# ✅ 저장 완료"),
            ui.TextDisplay("자판기 설정이 저장되었습니다."),
            accent_color=discord.Color.green()
        ))
        await interaction.response.edit_message(view=self)

    async def on_cancel(self, interaction: discord.Interaction):
        self.clear_items()
        self.add_item(ui.Container(
            ui.TextDisplay("# ❌ 취소됨"),
            ui.TextDisplay("변경사항이 저장되지 않았습니다."),
            accent_color=discord.Color.red()
        ))
        await interaction.response.edit_message(view=self)

class VendingEditModal(ui.Modal):
    value = ui.TextInput(label="값", max_length=500)

    def __init__(self, field: str, parent: "VendingEditView"):
        super().__init__(title=f"{field} 수정")
        self.field  = field
        self.parent = parent
        self.value.label = field
        if field == "내용":
            self.value.style = discord.TextStyle.paragraph

    async def on_submit(self, interaction: discord.Interaction):
        if self.field == "제목":
            self.parent.title   = self.value.value
        elif self.field == "내용":
            self.parent.desc    = self.value.value
        elif self.field == "사진":
            self.parent.img_url = self.value.value
        self.parent._render()
        await interaction.response.edit_message(view=self.parent)


async def get_server_config(guild_id: int) -> dict:
    async with aiosqlite.connect(db_path(guild_id)) as db:
        async with db.execute("SELECT key, value FROM server_config") as cur:
            rows = await cur.fetchall()
    return {r[0]: r[1] for r in rows}


@bot.tree.command(name="서버설정", description="서버 충전 설정을 합니다.")
@admin_check()
@app_commands.describe(계좌번호="계좌번호", 이름="예금주 이름", 최소충전금액="최소 충전 금액")
async def server_config_cmd(interaction: discord.Interaction, 계좌번호: str, 이름: str, 최소충전금액: int):
    async with aiosqlite.connect(db_path(interaction.guild.id)) as db:
        await db.execute("INSERT OR REPLACE INTO server_config (key, value) VALUES (?, ?)", ("account", 계좌번호))
        await db.execute("INSERT OR REPLACE INTO server_config (key, value) VALUES (?, ?)", ("owner",   이름))
        await db.execute("INSERT OR REPLACE INTO server_config (key, value) VALUES (?, ?)", ("min_charge", str(최소충전금액)))
        await db.commit()
    await interaction.response.send_message(
        f"설정 완료!\n계좌: `{계좌번호}` | 예금주: `{이름}` | 최소충전금액: `{최소충전금액:,}원`",
        ephemeral=True
    )


class ChargeModal(ui.Modal, title="충전하기"):
    depositor = ui.TextInput(label="입금자명", placeholder="예: 홍길동")
    amount    = ui.TextInput(label="충전할 금액", placeholder="예: 10000")

    def __init__(self, guild_id: int, user: discord.Member):
        super().__init__()
        self.guild_id = guild_id
        self.user     = user

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount.value.replace(",", ""))
        except ValueError:
            await interaction.response.send_message("금액은 숫자만 입력하세요.", ephemeral=True)
            return

        cfg = await get_server_config(self.guild_id)
        min_charge = int(cfg.get("min_charge", 0))

        if amount < min_charge:
            await interaction.response.send_message(
                f"최소 충전 금액은 {min_charge:,}원입니다.", ephemeral=True
            )
            return

        view = ChargeAgreeView(self.guild_id, self.user, self.depositor.value, amount, cfg)
        await interaction.response.send_message(view=view, ephemeral=True)


class ChargeAgreeView(ui.LayoutView):
    def __init__(self, guild_id, user, depositor, amount, cfg):
        super().__init__(timeout=180)
        self.guild_id  = guild_id
        self.user      = user
        self.depositor = depositor
        self.amount    = amount
        self.cfg       = cfg

        btn_agree = ui.Button(label="동의하기", style=discord.ButtonStyle.success, emoji="✅")
        btn_agree.callback = self.on_agree

        self.add_item(ui.Container(
            ui.TextDisplay("# 충전 전 안내"),
            ui.Separator(),
            ui.TextDisplay("불법 자금 송금 시 법적 대응합니다.\n제 3자 입금 금지 — 본인 계좌로만 입금 바랍니다.\n\n위 내용을 확인하셨으면 동의하기 버튼을 눌러주세요."),
            ui.Separator(),
            ui.ActionRow(btn_agree),
            accent_color=discord.Color.yellow()
        ))

    async def on_agree(self, interaction: discord.Interaction):
        account = self.cfg.get("account", "미설정")
        owner   = self.cfg.get("owner",   "미설정")

        info_view = ChargeInfoView(
            self.guild_id, self.user, self.depositor, self.amount, account, owner
        )
        await interaction.response.send_message(view=info_view, ephemeral=True)

        log_ch_id = await get_log_channel(interaction.guild.id, "충전확인")
        if not log_ch_id:
            return
        ch = interaction.guild.get_channel(log_ch_id)
        if not ch:
            return

        approve_view = ChargeApproveView(self.guild_id, self.user, self.depositor, self.amount)
        await ch.send(view=approve_view)


class ChargeInfoView(ui.LayoutView):
    def __init__(self, guild_id, user, depositor, amount, account, owner):
        super().__init__(timeout=None)
        self.guild_id  = guild_id
        self.user      = user
        self.depositor = depositor
        self.amount    = amount
        self.account   = account
        self.owner     = owner
        self._render(done=False)

    def _render(self, done: bool):
        self.clear_items()
        btn_done = ui.Button(label="입금 완료", style=discord.ButtonStyle.success, disabled=done)
        btn_done.callback = self.on_done

        self.add_item(ui.Container(
            ui.TextDisplay("# 충전 정보"),
            ui.Separator(),
            ui.TextDisplay(f"계좌번호\n{self.account} | {self.owner}"),
            ui.Separator(),
            ui.TextDisplay(f"입금자명　충전 금액\n{self.depositor}　　　{self.amount:,}원"),
            ui.Separator(),
            ui.ActionRow(btn_done),
            accent_color=discord.Color.blurple()
        ))

    async def on_done(self, interaction: discord.Interaction):
        self._render(done=True)
        await interaction.response.edit_message(view=self)

        log_ch_id = await get_log_channel(self.guild_id, "충전확인")
        if not log_ch_id:
            return
        ch = interaction.guild.get_channel(log_ch_id)
        if not ch:
            return
        await ch.send(f"💰 {self.user.mention}님이 입금 완료 버튼을 눌렀습니다. ({self.depositor} / {self.amount:,}원)")


class ChargeApproveView(ui.LayoutView):
    def __init__(self, guild_id, user, depositor, amount):
        super().__init__(timeout=None)
        self.guild_id  = guild_id
        self.user      = user
        self.depositor = depositor
        self.amount    = amount
        self._render(done=False)

    def _render(self, done: bool):
        self.clear_items()

        btn_approve = ui.Button(label="승인", style=discord.ButtonStyle.success, disabled=done)
        btn_reject  = ui.Button(label="거절", style=discord.ButtonStyle.danger,  disabled=done)
        btn_approve.callback = self.on_approve
        btn_reject.callback  = self.on_reject

        self.add_item(ui.Container(
            ui.TextDisplay("# 충전 요청"),
            ui.Separator(),
            ui.TextDisplay(f"닉네임　ID　　　　　　　　입금자명\n{self.user.display_name}　{self.user.id}　{self.depositor}"),
            ui.TextDisplay(f"금액\n{self.amount:,}원"),
            ui.Separator(),
            ui.ActionRow(btn_approve, btn_reject),
            accent_color=discord.Color.orange()
        ))

    async def on_approve(self, interaction: discord.Interaction):
        async with aiosqlite.connect(db_path(self.guild_id)) as db:
            await db.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id = ?",
                (self.amount, self.user.id)
            )
            await db.commit()

        self._render(done=True)
        await interaction.response.edit_message(view=self)

        try:
            await self.user.send(f"✅ {self.amount:,}원이 충전되었습니다.")
        except discord.Forbidden:
            pass

        log_ch_id = await get_log_channel(self.guild_id, "충전")
        if log_ch_id:
            ch = interaction.guild.get_channel(log_ch_id)
            if ch:
                await ch.send(embed=discord.Embed(
                    title="충전 완료",
                    description=f"{self.user.mention} | +{self.amount:,}원 | 승인자: {interaction.user.mention}",
                    color=discord.Color.green()
                ))

    async def on_reject(self, interaction: discord.Interaction):
        self._render(done=True)
        await interaction.response.edit_message(view=self)

        try:
            await self.user.send(f"❌ {self.amount:,}원 충전 요청이 거절되었습니다.")
        except discord.Forbidden:
            pass

bot.run(TOKEN)
