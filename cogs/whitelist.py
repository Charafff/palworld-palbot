import json
import os
import asyncio
import nextcord
from nextcord.ext import commands
from gamercon_async import GameRCON
import re

class PlayerInfoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_folder = 'data'
        self.player_data_file = os.path.join(self.data_folder, 'players.json')
        self.servers = self.load_servers_config()
        self.ensure_data_file()
        self.bot.loop.create_task(self.update_player_data_task())

    def load_servers_config(self):
        config_path = os.path.join(self.data_folder, 'config.json')
        with open(config_path) as config_file:
            return json.load(config_file)["PALWORLD_SERVERS"]

    def ensure_data_file(self):
        if not os.path.exists(self.player_data_file):
            with open(self.player_data_file, 'w') as file:
                json.dump({}, file)

    async def run_showplayers_command(self, server):
        try:
            async with GameRCON(server["RCON_HOST"], server["RCON_PORT"], server["RCON_PASS"], timeout=10) as pc:
                response = await asyncio.wait_for(pc.send("ShowPlayers"), timeout=10.0)
                return response
        except Exception as e:
            print(f"Error executing ShowPlayers command: {e}")
            return None

    async def update_player_data_task(self):
        while True:
            for server_name, server_info in self.servers.items():
                player_data = await self.run_showplayers_command(server_info)
                if player_data:
                    self.process_and_save_player_data(player_data)
                    await self.check_and_kick_non_whitelisted_players(server_info, player_data)
            await asyncio.sleep(20)

    async def check_and_kick_non_whitelisted_players(self, server, player_data):
        with open(self.player_data_file, 'r') as file:
            players = json.load(file)

        lines = player_data.split('\n')
        for line in lines[1:]:
            if not line.strip():
                continue

            parts = line.split(',')
            if len(parts) == 3:
                _, _, steamid = parts
                if steamid in players and not players[steamid].get("whitelist", False):
                    await self.kick_player(server, steamid)

    async def kick_player(self, server, steamid):
        try:
            async with GameRCON(server["RCON_HOST"], server["RCON_PORT"], server["RCON_PASS"], timeout=10) as pc:
                response = await asyncio.wait_for(pc.send(f"KickPlayer {steamid}"), timeout=10.0)
                print(f"Kicked non-whitelisted player {steamid}: {response}")
        except Exception as e:
            print(f"Error kicking player {steamid}: {e}")
            
    def is_valid_steamid(self, steamid):
        return bool(re.match(r'^7656119[0-9]{10}$', steamid))

    def sanitize_data(self, data):
        return re.sub(r'[^\x00-\x7F]+', '', data).strip()

    def process_and_save_player_data(self, data):
        if not data.strip():
            return

        with open(self.player_data_file, 'r') as file:
            existing_players = json.load(file)

        lines = data.split('\n')
        for line in lines[1:]:
            if line.strip():
                parts = line.split(',')
                if len(parts) == 3:
                    name, playeruid, steamid = parts
                    steamid = self.sanitize_data(steamid)
                    if not self.is_valid_steamid(steamid):
                        print(f"Ignored invalid or malformed SteamID: '{steamid}'")
                        continue
                    player_info = existing_players.get(steamid, {"whitelist": False})
                    player_info.update({"name": self.sanitize_data(name), "playeruid": playeruid})
                    existing_players[steamid] = player_info

        with open(self.player_data_file, 'w') as file:
            json.dump(existing_players, file)

    @nextcord.slash_command(description="Search the Paltopia user database", default_member_permissions=nextcord.Permissions(administrator=True))
    async def paldb(self, interaction: nextcord.Interaction):
        pass

    async def steamid_autocomplete(self, interaction: nextcord.Interaction, current: str):
        with open(self.player_data_file, 'r') as file:
            players = json.load(file)

        matches = [steamid for steamid in players if current.lower() in steamid.lower()]
        return matches[:25]

    @paldb.subcommand(name="steam", description="Find player by SteamID")
    async def search(self, interaction: nextcord.Interaction, steamid: str = nextcord.SlashOption(description="Enter SteamID", autocomplete=True)):
        with open(self.player_data_file, 'r') as file:
            players = json.load(file)

        player_info = players.get(steamid)
        if player_info:
            embed = nextcord.Embed(title="Player Information", color=nextcord.Color.blue())
            embed.add_field(name="Name", value=player_info["name"], inline=True)
            embed.add_field(name="Player UID", value=player_info["playeruid"], inline=True)
            embed.add_field(name="SteamID", value=steamid, inline=True)
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(f"No player found with SteamID {steamid}", ephemeral=True)

    @search.on_autocomplete("steamid")
    async def on_steamid_autocomplete(self, interaction: nextcord.Interaction, current: str):
        choices = await self.steamid_autocomplete(interaction, current)
        await interaction.response.send_autocomplete(choices)

    async def name_autocomplete(self, interaction: nextcord.Interaction, current: str):
        with open(self.player_data_file, 'r') as file:
            players = json.load(file)

        matches = [player["name"] for steamid, player in players.items() if player["name"] and current.lower() in player["name"].lower()]
        return matches[:25]

    @paldb.subcommand(name="name", description="Find player by name")
    async def searchname(self, interaction: nextcord.Interaction, 
                         name: str = nextcord.SlashOption(description="Enter player name", autocomplete=True)):
        with open(self.player_data_file, 'r') as file:
            players = json.load(file)

        player_info = None
        player_steamid = None
        for steamid, player in players.items():
            if player["name"].lower() == name.lower():
                player_info = player
                player_steamid = steamid
                break

        if player_info and player_steamid:
            embed = nextcord.Embed(title="Player Information", color=nextcord.Color.blue())
            embed.add_field(name="Name", value=player_info["name"], inline=True)
            embed.add_field(name="Player UID", value=player_info["playeruid"], inline=True)
            embed.add_field(name="SteamID", value=player_steamid, inline=True)
            embed.add_field(name="Whitelist", value=player_info["whitelist"], inline=True)
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(f"No player found with name '{name}'", ephemeral=True)

    @searchname.on_autocomplete("name")
    async def on_name_autocomplete(self, interaction: nextcord.Interaction, current: str):
        choices = await self.name_autocomplete(interaction, current)
        await interaction.response.send_autocomplete(choices)

    @paldb.subcommand(name="whitelistadd", description="Add player to whitelist")
    async def whitelist_add(self, interaction: nextcord.Interaction, steamid: str):
        with open(self.player_data_file, 'r+') as file:
            players = json.load(file)

            if steamid not in players:
                players[steamid] = {"name": None, "playeruid": None, "whitelist": True}
                file.seek(0)
                json.dump(players, file)
                file.truncate()
                await interaction.response.send_message(f"Player {steamid} added to whitelist and will be fully registered upon joining.", ephemeral=True)
            else:
                players[steamid]["whitelist"] = True
                file.seek(0)
                json.dump(players, file)
                file.truncate()
                await interaction.response.send_message(f"Player {steamid} added to whitelist.", ephemeral=True)

    @paldb.subcommand(name="whitelistremove", description="Remove player from whitelist")
    async def whitelist_remove(self, interaction: nextcord.Interaction, steamid: str):
        with open(self.player_data_file, 'r') as file:
            players = json.load(file)

        if steamid in players and players[steamid]["whitelist"]:
            players[steamid]["whitelist"] = False
            with open(self.player_data_file, 'w') as file:
                json.dump(players, file)
            await interaction.response.send_message(f"Player {steamid} removed from whitelist.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Player {steamid} not found or not on whitelist.", ephemeral=True)

def setup(bot):
    bot.add_cog(PlayerInfoCog(bot))