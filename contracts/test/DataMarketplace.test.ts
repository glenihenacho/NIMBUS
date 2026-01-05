import { expect } from "chai";
import { ethers, upgrades } from "hardhat";
import { PAT, DataMarketplace } from "../typechain-types";
import { SignerWithAddress } from "@nomicfoundation/hardhat-ethers/signers";

describe("DataMarketplace", function () {
  let pat: PAT;
  let marketplace: DataMarketplace;
  let owner: SignerWithAddress;
  let broker: SignerWithAddress;
  let provider: SignerWithAddress;
  let consumer: SignerWithAddress;
  let usersPool: SignerWithAddress;

  const BROKER_MARGIN_BPS = 3000; // 30%
  const SEGMENT_PRICE = ethers.parseEther("100"); // 100 PAT

  beforeEach(async function () {
    [owner, broker, provider, consumer, usersPool] = await ethers.getSigners();

    // Deploy PAT token
    const PATFactory = await ethers.getContractFactory("PAT");
    pat = await PATFactory.deploy();
    await pat.waitForDeployment();

    // Deploy DataMarketplace as upgradeable proxy
    const MarketplaceFactory = await ethers.getContractFactory("DataMarketplace");
    marketplace = await upgrades.deployProxy(
      MarketplaceFactory,
      [await pat.getAddress(), broker.address, usersPool.address, BROKER_MARGIN_BPS],
      { kind: "uups" }
    ) as unknown as DataMarketplace;
    await marketplace.waitForDeployment();

    // Transfer some PAT to consumer for testing
    await pat.transfer(consumer.address, ethers.parseEther("1000"));
  });

  describe("Deployment", function () {
    it("Should set correct initial configuration", async function () {
      expect(await marketplace.brokerWallet()).to.equal(broker.address);
      expect(await marketplace.usersPoolWallet()).to.equal(usersPool.address);
      expect(await marketplace.brokerMarginBps()).to.equal(BROKER_MARGIN_BPS);
      expect(await marketplace.getPhaseString()).to.equal("UTILITY");
      expect(await marketplace.paused()).to.equal(false);
    });

    it("Should be upgradeable", async function () {
      const implAddress = await marketplace.getImplementation();
      expect(implAddress).to.not.equal(ethers.ZeroAddress);
    });
  });

  describe("Segment Creation", function () {
    it("Should create a segment", async function () {
      const tx = await marketplace.connect(provider).createSegment(
        0, // PURCHASE_INTENT
        7, // 7 days
        7500, // 75% confidence
        SEGMENT_PRICE
      );

      await expect(tx)
        .to.emit(marketplace, "SegmentCreated")
        .withArgs(0, provider.address, 0, SEGMENT_PRICE);

      const segment = await marketplace.getSegment(0);
      expect(segment.segmentType).to.equal(0);
      expect(segment.windowDays).to.equal(7);
      expect(segment.confidenceBps).to.equal(7500);
      expect(segment.askPrice).to.equal(SEGMENT_PRICE);
      expect(segment.provider).to.equal(provider.address);
      expect(segment.active).to.equal(true);
    });

    it("Should reject invalid window", async function () {
      await expect(
        marketplace.connect(provider).createSegment(0, 0, 7500, SEGMENT_PRICE)
      ).to.be.revertedWith("Invalid window");

      await expect(
        marketplace.connect(provider).createSegment(0, 31, 7500, SEGMENT_PRICE)
      ).to.be.revertedWith("Invalid window");
    });
  });

  describe("Atomic Settlement", function () {
    beforeEach(async function () {
      await marketplace.connect(provider).createSegment(0, 7, 7500, SEGMENT_PRICE);
      await pat.connect(consumer).approve(await marketplace.getAddress(), SEGMENT_PRICE);
    });

    it("Should atomically settle purchase and record earnings", async function () {
      const brokerBalanceBefore = await pat.balanceOf(broker.address);
      const consumerBalanceBefore = await pat.balanceOf(consumer.address);
      const providerEarningsBefore = await marketplace.userEarnings(provider.address);

      const expectedBrokerSpread = (SEGMENT_PRICE * BigInt(BROKER_MARGIN_BPS)) / 10000n;
      const expectedProviderPayout = SEGMENT_PRICE - expectedBrokerSpread;

      const tx = await marketplace.connect(consumer).buySegment(0);

      await expect(tx)
        .to.emit(marketplace, "SegmentPurchased")
        .withArgs(0, consumer.address, provider.address, SEGMENT_PRICE, expectedProviderPayout, expectedBrokerSpread);

      await expect(tx).to.emit(marketplace, "PayoutRecorded");

      expect(await marketplace.userEarnings(provider.address)).to.equal(
        providerEarningsBefore + expectedProviderPayout
      );
      expect(await pat.balanceOf(broker.address)).to.equal(
        brokerBalanceBefore + expectedBrokerSpread
      );
      expect(await pat.balanceOf(consumer.address)).to.equal(
        consumerBalanceBefore - SEGMENT_PRICE
      );
      expect(await marketplace.hasAccess(consumer.address, 0)).to.equal(true);
    });

    it("Should allow provider to withdraw earnings", async function () {
      await marketplace.connect(consumer).buySegment(0);

      const expectedBrokerSpread = (SEGMENT_PRICE * BigInt(BROKER_MARGIN_BPS)) / 10000n;
      const expectedProviderPayout = SEGMENT_PRICE - expectedBrokerSpread;

      expect(await marketplace.userEarnings(provider.address)).to.equal(expectedProviderPayout);

      const providerBalanceBefore = await pat.balanceOf(provider.address);
      const tx = await marketplace.connect(provider).withdrawEarnings(expectedProviderPayout);

      await expect(tx).to.emit(marketplace, "Withdrawal");

      expect(await pat.balanceOf(provider.address)).to.equal(
        providerBalanceBefore + expectedProviderPayout
      );
      expect(await marketplace.userEarnings(provider.address)).to.equal(0);
    });

    it("Should allow withdrawAllEarnings", async function () {
      await marketplace.connect(consumer).buySegment(0);

      const expectedBrokerSpread = (SEGMENT_PRICE * BigInt(BROKER_MARGIN_BPS)) / 10000n;
      const expectedProviderPayout = SEGMENT_PRICE - expectedBrokerSpread;

      const providerBalanceBefore = await pat.balanceOf(provider.address);
      await marketplace.connect(provider).withdrawAllEarnings();

      expect(await pat.balanceOf(provider.address)).to.equal(
        providerBalanceBefore + expectedProviderPayout
      );
      expect(await marketplace.userEarnings(provider.address)).to.equal(0);
    });

    it("Should reject withdrawal with insufficient earnings", async function () {
      await expect(
        marketplace.connect(provider).withdrawEarnings(ethers.parseEther("1000"))
      ).to.be.revertedWithCustomError(marketplace, "InsufficientEarnings");
    });

    it("Should calculate split correctly", async function () {
      const [providerPayout, brokerSpread] = await marketplace.calculateSplit(SEGMENT_PRICE);

      expect(brokerSpread).to.equal((SEGMENT_PRICE * BigInt(BROKER_MARGIN_BPS)) / 10000n);
      expect(providerPayout).to.equal(SEGMENT_PRICE - brokerSpread);
      expect(providerPayout + brokerSpread).to.equal(SEGMENT_PRICE);
    });

    it("Should reject purchase without approval", async function () {
      await marketplace.connect(provider).createSegment(0, 7, 7500, SEGMENT_PRICE);

      await expect(
        marketplace.connect(consumer).buySegment(1)
      ).to.be.revertedWithCustomError(marketplace, "InsufficientAllowance");
    });

    it("Should reject duplicate purchase", async function () {
      await marketplace.connect(consumer).buySegment(0);
      await pat.connect(consumer).approve(await marketplace.getAddress(), SEGMENT_PRICE);

      await expect(
        marketplace.connect(consumer).buySegment(0)
      ).to.be.revertedWithCustomError(marketplace, "AlreadyHasAccess");
    });

    it("Should reject purchase of inactive segment", async function () {
      await marketplace.connect(provider).deactivateSegment(0);

      await expect(
        marketplace.connect(consumer).buySegment(0)
      ).to.be.revertedWithCustomError(marketplace, "SegmentNotActive");
    });
  });

  describe("Admin Functions", function () {
    it("Should update broker margin", async function () {
      await marketplace.setBrokerMargin(2000);
      expect(await marketplace.brokerMarginBps()).to.equal(2000);
    });

    it("Should reject margin > 50%", async function () {
      await expect(
        marketplace.setBrokerMargin(5001)
      ).to.be.revertedWithCustomError(marketplace, "InvalidConfiguration");
    });

    it("Should update broker wallet", async function () {
      await marketplace.setBrokerWallet(consumer.address);
      expect(await marketplace.brokerWallet()).to.equal(consumer.address);
    });

    it("Should advance phase", async function () {
      expect(await marketplace.getPhaseString()).to.equal("UTILITY");

      await marketplace.advancePhase();
      expect(await marketplace.getPhaseString()).to.equal("FORWARDS");

      await marketplace.advancePhase();
      expect(await marketplace.getPhaseString()).to.equal("SYNTHETICS");

      await marketplace.advancePhase();
      expect(await marketplace.getPhaseString()).to.equal("SPECULATION");

      await expect(marketplace.advancePhase()).to.be.revertedWith("Already at final phase");
    });

    it("Should pause and unpause", async function () {
      await marketplace.setPaused(true);
      expect(await marketplace.paused()).to.equal(true);

      await expect(
        marketplace.connect(provider).createSegment(0, 7, 7500, SEGMENT_PRICE)
      ).to.be.revertedWithCustomError(marketplace, "MarketPaused");

      await marketplace.setPaused(false);
      await marketplace.connect(provider).createSegment(0, 7, 7500, SEGMENT_PRICE);
    });

    it("Should reject non-owner admin calls", async function () {
      await expect(
        marketplace.connect(consumer).setBrokerMargin(2000)
      ).to.be.revertedWithCustomError(marketplace, "OwnableUnauthorizedAccount");
    });
  });

  describe("Contract Upgrade (updateBrokerContract)", function () {
    it("Should allow owner to upgrade contract", async function () {
      const MarketplaceV2Factory = await ethers.getContractFactory("DataMarketplace");

      // Deploy new implementation
      const newImpl = await MarketplaceV2Factory.deploy();
      await newImpl.waitForDeployment();

      // Upgrade
      const tx = await marketplace.updateBrokerContract(await newImpl.getAddress());

      await expect(tx).to.emit(marketplace, "BrokerContractUpdated");
    });

    it("Should reject upgrade from non-owner", async function () {
      const MarketplaceV2Factory = await ethers.getContractFactory("DataMarketplace");
      const newImpl = await MarketplaceV2Factory.deploy();
      await newImpl.waitForDeployment();

      await expect(
        marketplace.connect(consumer).updateBrokerContract(await newImpl.getAddress())
      ).to.be.revertedWithCustomError(marketplace, "OwnableUnauthorizedAccount");
    });

    it("Should preserve state after upgrade", async function () {
      // Create segment before upgrade
      await marketplace.connect(provider).createSegment(0, 7, 7500, SEGMENT_PRICE);

      const MarketplaceV2Factory = await ethers.getContractFactory("DataMarketplace");
      const newImpl = await MarketplaceV2Factory.deploy();
      await newImpl.waitForDeployment();

      await marketplace.updateBrokerContract(await newImpl.getAddress());

      // State should be preserved
      const segment = await marketplace.getSegment(0);
      expect(segment.askPrice).to.equal(SEGMENT_PRICE);
      expect(segment.provider).to.equal(provider.address);
      expect(await marketplace.brokerMarginBps()).to.equal(BROKER_MARGIN_BPS);
    });
  });

  describe("Provider Functions", function () {
    beforeEach(async function () {
      await marketplace.connect(provider).createSegment(0, 7, 7500, SEGMENT_PRICE);
    });

    it("Should update segment price", async function () {
      const newPrice = ethers.parseEther("150");
      await marketplace.connect(provider).updateSegmentPrice(0, newPrice);

      const segment = await marketplace.getSegment(0);
      expect(segment.askPrice).to.equal(newPrice);
    });

    it("Should deactivate segment", async function () {
      await marketplace.connect(provider).deactivateSegment(0);

      const segment = await marketplace.getSegment(0);
      expect(segment.active).to.equal(false);
    });

    it("Should reject non-provider updates", async function () {
      await expect(
        marketplace.connect(consumer).updateSegmentPrice(0, SEGMENT_PRICE)
      ).to.be.revertedWith("Not provider");

      await expect(
        marketplace.connect(consumer).deactivateSegment(0)
      ).to.be.revertedWith("Not provider");
    });
  });
});
