import nextcord
from nextcord.ext import commands
import json

class InviteRewards(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.invites = {}
        self.file_path = "economy_data.json"
        self.config_path = "config.json"
        self.config = self.load_config()

    def load_config(self):
        with open(self.config_path, 'r') as f:
            return json.load(f).get("ECONOMY_SETTINGS", {})

    def read_data(self):
        with open(self.file_path, 'r') as f:
            return json.load(f)

    def write_data(self, data):
        with open(self.file_path, 'w') as f:
            json.dump(data, f, indent=4)

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            self.invites[guild.id] = await guild.invites()

    @commands.Cog.listener()
    async def on_member_join(self, member):
        invites_before_join = self.invites[member.guild.id]
        invites_after_join = await member.guild.invites()

        for invite in invites_before_join:
            if invite.uses < next((i.uses for i in invites_after_join if i.code == invite.code), invite.uses):
                inviter = invite.inviter
                data = self.read_data()
                user_id = str(inviter.id)
                invite_reward = self.config.get('invite_reward', 100)

                if user_id not in data:
                    data[user_id] = {"balance": invite_reward}
                else:
                    data[user_id]["balance"] += invite_reward

                self.write_data(data)
                await inviter.send(f"Thank you for inviting a new member! You have received {invite_reward} {self.config['currency']}.")
                break

        self.invites[member.guild.id] = invites_after_join

def setup(bot):
    bot.add_cog(InviteRewards(bot))
