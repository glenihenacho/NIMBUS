import { expect } from "chai";
import { ethers } from "hardhat";
import { PAT } from "../typechain-types";
import { SignerWithAddress } from "@nomicfoundation/hardhat-ethers/signers";

describe("PAT Token", function () {
  let pat: PAT;
  let owner: SignerWithAddress;
  let treasury: SignerWithAddress;
  let ecosystem: SignerWithAddress;
  let ico: SignerWithAddress;
  let teamVesting: SignerWithAddress;

  const TOTAL_SUPPLY = ethers.parseEther("555222888");
  const SIX_MONTHS = 180 * 24 * 60 * 60; // 180 days in seconds

  beforeEach(async function () {
    [owner, treasury, ecosystem, ico, teamVesting] = await ethers.getSigners();

    const PATFactory = await ethers.getContractFactory("PAT");
    pat = await PATFactory.deploy();
    await pat.waitForDeployment();
  });

  describe("Deployment", function () {
    it("Should have correct name and symbol", async function () {
      expect(await pat.name()).to.equal("PAT");
      expect(await pat.symbol()).to.equal("PAT");
    });

    it("Should mint total supply to owner", async function () {
      expect(await pat.totalSupply()).to.equal(TOTAL_SUPPLY);
      expect(await pat.balanceOf(owner.address)).to.equal(TOTAL_SUPPLY);
    });

    it("Should have correct allocation constants", async function () {
      expect(await pat.TREASURY_BPS()).to.equal(5000);
      expect(await pat.ECOSYSTEM_BPS()).to.equal(3000);
      expect(await pat.ICO_BPS()).to.equal(1000);
      expect(await pat.TEAM_BPS()).to.equal(1000);
    });
  });

  describe("Allocation Distribution", function () {
    it("Should distribute allocation correctly", async function () {
      await pat.distributeAllocation(
        treasury.address,
        ecosystem.address,
        ico.address,
        teamVesting.address,
        SIX_MONTHS
      );

      // Check treasury (50%)
      const treasuryBalance = await pat.balanceOf(treasury.address);
      expect(treasuryBalance).to.equal(ethers.parseEther("277611444"));

      // Check ecosystem (30%)
      const ecosystemBalance = await pat.balanceOf(ecosystem.address);
      expect(ecosystemBalance).to.equal(ethers.parseEther("166566866.4"));

      // Check ICO (10%)
      const icoBalance = await pat.balanceOf(ico.address);
      expect(icoBalance).to.equal(ethers.parseEther("55522288.8"));
    });

    it("Should fail if vesting duration is too short", async function () {
      await expect(
        pat.distributeAllocation(
          treasury.address,
          ecosystem.address,
          ico.address,
          teamVesting.address,
          100 // Less than 180 days
        )
      ).to.be.revertedWith("Vesting too short");
    });

    it("Should fail if called twice", async function () {
      await pat.distributeAllocation(
        treasury.address,
        ecosystem.address,
        ico.address,
        teamVesting.address,
        SIX_MONTHS
      );

      await expect(
        pat.distributeAllocation(
          treasury.address,
          ecosystem.address,
          ico.address,
          teamVesting.address,
          SIX_MONTHS
        )
      ).to.be.revertedWith("Already distributed");
    });
  });

  describe("Team Vesting", function () {
    beforeEach(async function () {
      await pat.distributeAllocation(
        treasury.address,
        ecosystem.address,
        ico.address,
        teamVesting.address,
        SIX_MONTHS
      );
    });

    it("Should have no releasable tokens initially", async function () {
      expect(await pat.releasableTeamTokens()).to.equal(0);
    });

    it("Should release tokens after time passes", async function () {
      // Fast forward 3 months (half of vesting period)
      await ethers.provider.send("evm_increaseTime", [SIX_MONTHS / 2]);
      await ethers.provider.send("evm_mine", []);

      const releasable = await pat.releasableTeamTokens();
      expect(releasable).to.be.gt(0);
    });
  });

  describe("ERC20 Functions", function () {
    it("Should allow transfers", async function () {
      const amount = ethers.parseEther("1000");
      await pat.transfer(treasury.address, amount);
      expect(await pat.balanceOf(treasury.address)).to.equal(amount);
    });

    it("Should allow burning", async function () {
      const burnAmount = ethers.parseEther("1000");
      await pat.burn(burnAmount);
      expect(await pat.totalSupply()).to.equal(TOTAL_SUPPLY - burnAmount);
    });
  });
});
