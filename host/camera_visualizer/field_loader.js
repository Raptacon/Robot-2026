/**
 * Field model loader for the camera visualizer.
 *
 * Loads FRC field GLB models from the server (which proxies from
 * AdvantageScope's GitHub assets), places AprilTags at official
 * positions, and manages scene mode switching.
 */

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';

const TAG_SIZE = 0.1651;  // 6.5" AprilTag in meters

export class FieldManager {
  constructor(scene, envGroup) {
    this.scene = scene;
    this.envGroup = envGroup;       // environment group (grids, tags)
    this.fieldModel = null;         // THREE.Group for the loaded field
    this.fieldConfig = null;        // parsed config.json
    this.fieldTags = [];            // AprilTag meshes placed on field
    this.currentMode = 'robot-view';
    this.onStatusChange = null;
    this.onFieldLoaded = null;     // callback({ lengthM, widthM, robotX, robotY })

    this._loader = new GLTFLoader();
    const draco = new DRACOLoader();
    draco.setDecoderPath(
      'https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/libs/draco/'
    );
    this._loader.setDRACOLoader(draco);

    // Reference to the default environment elements (grids, fake tags)
    this._defaultEnvChildren = [];
  }

  /**
   * Save references to the default environment (grids, tag ring)
   * so we can hide/show them when switching modes.
   */
  captureDefaultEnv() {
    this._defaultEnvChildren = [...this.envGroup.children];
  }

  /**
   * Fetch the list of available fields from the server.
   */
  async fetchFieldList() {
    const res = await fetch('/api/field-list');
    return res.json();
  }

  /**
   * Fetch real AprilTag positions from the server (robotpy_apriltag data).
   */
  async fetchFieldTags() {
    const res = await fetch('/api/field-tags');
    return res.json();
  }

  /**
   * Switch to a scene mode.
   */
  async setMode(modeId, robotGroup) {
    this._setStatus(`Loading ${modeId}...`);

    // Unload previous field
    this._unloadField();

    this.currentMode = modeId;

    if (modeId === 'robot-view') {
      // Show default environment (grids + fake tag ring)
      this._showDefaultEnv(true);
      // Robot at origin
      robotGroup.position.set(0, 0, 0);
      robotGroup.rotation.set(0, 0, 0);
      this._setStatus('Robot View');
      return;
    }

    if (modeId === 'evergreen') {
      this._showDefaultEnv(false);
      await this._buildEvergreenField(robotGroup);
      this._setStatus('Evergreen Field');
      return;
    }

    if (modeId === 'cat-box') {
      this._showDefaultEnv(false);
      this._buildCatBox();
      // Robot at center
      robotGroup.position.set(0, 0, 0);
      robotGroup.rotation.set(0, 0, 0);
      this._setStatus('Cat Box');
      return;
    }

    // Field mode — hide default env, load field model
    this._showDefaultEnv(false);

    try {
      // Fetch field config
      const configRes = await fetch(`/api/field/${modeId}.json`);
      if (!configRes.ok) throw new Error(`Config not found: ${configRes.status}`);
      this.fieldConfig = await configRes.json();

      // Load field GLB
      const glb = await new Promise((resolve, reject) => {
        this._loader.load(
          `/api/field/${modeId}.glb`,
          resolve,
          (progress) => {
            if (progress.total > 0) {
              const pct = Math.round((progress.loaded / progress.total) * 100);
              this._setStatus(`Loading field... ${pct}%`);
            }
          },
          reject,
        );
      });

      const root = glb.scene;

      // Apply rotations from config (AdvantageScope convention)
      if (this.fieldConfig.rotations) {
        for (const rot of this.fieldConfig.rotations) {
          const rad = THREE.MathUtils.degToRad(rot.degrees);
          if (rot.axis === 'x') root.rotation.x += rad;
          else if (rot.axis === 'y') root.rotation.y += rad;
          else if (rot.axis === 'z') root.rotation.z += rad;
        }
      }

      // AdvantageScope "wall-blue" coordinate system has origin at field center.
      // WPILib NWU has origin at blue alliance wall corner.
      // Offset: field center is at (fieldLength/2, fieldWidth/2, 0) in WPILib coords.
      const fieldLengthM = this.fieldConfig.widthInches * 0.0254;  // confusingly named in config
      const fieldWidthM = this.fieldConfig.heightInches * 0.0254;
      root.position.set(fieldLengthM / 2, fieldWidthM / 2, 0);

      // Reduce metalness on all PBR materials so they respond to ambient light
      // instead of only reflecting the (missing) environment map
      root.traverse((obj) => {
        if (obj.isMesh && obj.material) {
          const mat = obj.material;
          if (mat.metalness !== undefined) {
            mat.metalness = Math.min(mat.metalness, 0.3);
            mat.roughness = Math.max(mat.roughness, 0.5);
          }
        }
      });

      this.fieldModel = root;
      this.scene.add(root);

      // Add field grid
      this._addFieldGrid(fieldLengthM, fieldWidthM);

      // Place real AprilTags
      await this._placeFieldTags();

      // Position robot at field center
      robotGroup.position.set(fieldLengthM / 2, fieldWidthM / 2, 0);

      const tagCount = this.fieldTags.length;
      this._setStatus(`${this.fieldConfig.name} (${tagCount} tags)`);

      if (this.onFieldLoaded) {
        this.onFieldLoaded({
          lengthM: fieldLengthM, widthM: fieldWidthM,
          robotX: fieldLengthM / 2, robotY: fieldWidthM / 2,
        });
      }

    } catch (e) {
      this._setStatus(`Error: ${e.message}`);
      console.error('[Field] Load error:', e);
    }
  }

  // ── AprilTag placement ──────────────────────────────────────────────

  async _placeFieldTags() {
    const tagData = await this.fetchFieldTags();
    if (!tagData.tags || tagData.tags.length === 0) return;

    for (const tag of tagData.tags) {
      const group = new THREE.Group();
      group.position.set(tag.x, tag.y, tag.z);

      // Tag face (white square)
      const faceGeo = new THREE.PlaneGeometry(TAG_SIZE, TAG_SIZE);
      const faceMat = new THREE.MeshBasicMaterial({
        color: 0xffffff, side: THREE.DoubleSide,
      });
      const face = new THREE.Mesh(faceGeo, faceMat);

      // Rotate to face the correct direction based on yaw
      const yawRad = THREE.MathUtils.degToRad(tag.yaw_deg);
      face.rotation.z = yawRad;
      // PlaneGeometry is in XY plane; for a vertical tag we keep it as-is
      // since the tag Z position already places it at the right height.
      // The plane needs to face outward — rotate around Z for yaw.
      // Actually, we need to make the plane vertical and face the yaw direction.
      // PlaneGeometry faces +Z by default. We want it to face the yaw direction.
      group.rotation.set(0, 0, yawRad);
      face.rotation.set(0, Math.PI / 2, 0);  // make vertical, facing +X in local

      group.add(face);

      // Inner dark pattern
      const innerGeo = new THREE.PlaneGeometry(TAG_SIZE * 0.7, TAG_SIZE * 0.7);
      const innerMat = new THREE.MeshBasicMaterial({
        color: 0x111111, side: THREE.DoubleSide,
      });
      const inner = new THREE.Mesh(innerGeo, innerMat);
      inner.rotation.copy(face.rotation);
      inner.position.x = 0.001;
      group.add(inner);

      // ID label
      const canvas = document.createElement('canvas');
      canvas.width = 64; canvas.height = 32;
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#000';
      ctx.fillRect(0, 0, 64, 32);
      ctx.fillStyle = '#fff';
      ctx.font = 'bold 22px monospace';
      ctx.textAlign = 'center';
      ctx.fillText(`${tag.id}`, 32, 22);
      const tex = new THREE.CanvasTexture(canvas);
      const spriteMat = new THREE.SpriteMaterial({ map: tex });
      const sprite = new THREE.Sprite(spriteMat);
      sprite.scale.set(0.12, 0.06, 1);
      sprite.position.set(0, 0, TAG_SIZE * 0.7);
      group.add(sprite);

      group.userData = { tagId: tag.id, isFieldTag: true };
      this.scene.add(group);
      this.fieldTags.push(group);
    }
  }

  // ── Field grid ──────────────────────────────────────────────────────

  _addFieldGrid(lengthM, widthM) {
    // Field outline
    const outlineGeo = new THREE.BufferGeometry();
    const pts = [
      new THREE.Vector3(0, 0, 0.001),
      new THREE.Vector3(lengthM, 0, 0.001),
      new THREE.Vector3(lengthM, widthM, 0.001),
      new THREE.Vector3(0, widthM, 0.001),
      new THREE.Vector3(0, 0, 0.001),
    ];
    outlineGeo.setFromPoints(pts);
    const outlineMat = new THREE.LineBasicMaterial({ color: 0x446688 });
    const outline = new THREE.Line(outlineGeo, outlineMat);
    outline.userData = { isFieldElement: true };
    this.scene.add(outline);

    // Grid
    const gridSize = Math.max(lengthM, widthM);
    const grid = new THREE.GridHelper(gridSize, Math.round(gridSize), 0x222244, 0x1a1a2e);
    grid.rotation.x = Math.PI / 2;
    grid.position.set(lengthM / 2, widthM / 2, 0);
    grid.userData = { isFieldElement: true };
    this.scene.add(grid);

    // Origin marker (blue alliance corner)
    const originMarker = new THREE.ArrowHelper(
      new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 0, 0.01),
      0.5, 0x4488ff, 0.06, 0.04
    );
    originMarker.userData = { isFieldElement: true };
    this.scene.add(originMarker);
    const originLabel = this._makeSprite('ORIGIN (Blue)', 0x4488ff);
    originLabel.position.set(0.3, -0.15, 0.01);
    originLabel.userData = { isFieldElement: true };
    this.scene.add(originLabel);
  }

  // ── Evergreen field (programmatic) ───────────────────────────────────

  async _buildEvergreenField(robotGroup) {
    // Standard FRC field: 54'1" x 26'7.5" = 16.4846m x 8.1153m
    const fieldLength = 16.4846;
    const fieldWidth = 8.1153;
    const wallHeight = 0.508;  // ~20" high walls

    // Carpet
    const carpetGeo = new THREE.PlaneGeometry(fieldLength, fieldWidth);
    const carpetMat = new THREE.MeshPhongMaterial({ color: 0x555555, side: THREE.DoubleSide });
    const carpet = new THREE.Mesh(carpetGeo, carpetMat);
    carpet.position.set(fieldLength / 2, fieldWidth / 2, 0);
    carpet.userData = { isFieldElement: true };
    this.scene.add(carpet);

    // Walls (4 sides)
    const wallMat = new THREE.MeshPhongMaterial({ color: 0x888888, side: THREE.DoubleSide });
    const walls = [
      // Blue wall (X=0)
      { w: fieldWidth, pos: [0, fieldWidth / 2, wallHeight / 2], rot: [0, Math.PI / 2, 0] },
      // Red wall (X=fieldLength)
      { w: fieldWidth, pos: [fieldLength, fieldWidth / 2, wallHeight / 2], rot: [0, Math.PI / 2, 0] },
      // Side wall (Y=0)
      { w: fieldLength, pos: [fieldLength / 2, 0, wallHeight / 2], rot: [0, 0, 0] },
      // Side wall (Y=fieldWidth)
      { w: fieldLength, pos: [fieldLength / 2, fieldWidth, wallHeight / 2], rot: [0, 0, 0] },
    ];
    walls.forEach(({ w, pos, rot }) => {
      const geo = new THREE.PlaneGeometry(w, wallHeight);
      const mesh = new THREE.Mesh(geo, wallMat);
      mesh.position.set(...pos);
      mesh.rotation.set(...rot);
      mesh.userData = { isFieldElement: true };
      this.scene.add(mesh);
    });

    // Blue alliance markers
    const blueMarker = new THREE.Mesh(
      new THREE.PlaneGeometry(0.05, fieldWidth * 0.3),
      new THREE.MeshBasicMaterial({ color: 0x0044ff, side: THREE.DoubleSide })
    );
    blueMarker.position.set(0.01, fieldWidth / 2, wallHeight / 2);
    blueMarker.rotation.y = Math.PI / 2;
    blueMarker.userData = { isFieldElement: true };
    this.scene.add(blueMarker);

    // Red alliance marker
    const redMarker = new THREE.Mesh(
      new THREE.PlaneGeometry(0.05, fieldWidth * 0.3),
      new THREE.MeshBasicMaterial({ color: 0xff0000, side: THREE.DoubleSide })
    );
    redMarker.position.set(fieldLength - 0.01, fieldWidth / 2, wallHeight / 2);
    redMarker.rotation.y = Math.PI / 2;
    redMarker.userData = { isFieldElement: true };
    this.scene.add(redMarker);

    // Grid and outline
    this._addFieldGrid(fieldLength, fieldWidth);

    // Place real AprilTags from robotpy_apriltag
    await this._placeFieldTags();

    // Robot at field center
    robotGroup.position.set(fieldLength / 2, fieldWidth / 2, 0);

    if (this.onFieldLoaded) {
      this.onFieldLoaded({
        lengthM: fieldLength, widthM: fieldWidth,
        robotX: fieldLength / 2, robotY: fieldWidth / 2,
      });
    }
  }

  // ── Cat Box ─────────────────────────────────────────────────────────

  _buildCatBox() {
    const size = 3;  // 3m cube
    const half = size / 2;

    // 6 faces with cat pictures (placeholder colored planes)
    const catColors = [0xff8844, 0x88ff44, 0x4488ff, 0xff44ff, 0xffff44, 0x44ffff];
    const catNames = ['Whiskers', 'Mittens', 'Shadow', 'Luna', 'Mochi', 'Biscuit'];
    const faces = [
      { pos: [half, 0, half], rot: [0, Math.PI / 2, 0] },    // +X
      { pos: [-half, 0, half], rot: [0, -Math.PI / 2, 0] },  // -X
      { pos: [0, half, half], rot: [-Math.PI / 2, 0, 0] },   // +Y
      { pos: [0, -half, half], rot: [Math.PI / 2, 0, 0] },   // -Y
      { pos: [0, 0, size], rot: [0, 0, 0] },                  // +Z (top)
      { pos: [0, 0, 0], rot: [Math.PI, 0, 0] },               // -Z (bottom)
    ];

    faces.forEach((face, i) => {
      const geo = new THREE.PlaneGeometry(size, size);

      // Create a cat face texture
      const canvas = document.createElement('canvas');
      canvas.width = 256; canvas.height = 256;
      const ctx = canvas.getContext('2d');

      // Background
      const color = catColors[i];
      ctx.fillStyle = `#${color.toString(16).padStart(6, '0')}`;
      ctx.fillRect(0, 0, 256, 256);

      // Simple cat face
      ctx.fillStyle = '#000';
      ctx.font = '120px serif';
      ctx.textAlign = 'center';
      ctx.fillText('\u{1F431}', 128, 150);  // cat face emoji
      ctx.font = 'bold 24px sans-serif';
      ctx.fillStyle = '#fff';
      ctx.fillText(catNames[i], 128, 240);

      const tex = new THREE.CanvasTexture(canvas);
      const mat = new THREE.MeshBasicMaterial({
        map: tex, side: THREE.DoubleSide, transparent: true, opacity: 0.8,
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(...face.pos);
      mesh.rotation.set(...face.rot);
      mesh.userData = { isFieldElement: true, isCatBox: true };
      this.scene.add(mesh);
    });
  }

  // ── Helpers ─────────────────────────────────────────────────────────

  _showDefaultEnv(show) {
    this._defaultEnvChildren.forEach(child => {
      child.visible = show;
    });
  }

  _unloadField() {
    // Remove field model
    if (this.fieldModel) {
      this.fieldModel.traverse(obj => {
        if (obj.isMesh) {
          obj.geometry.dispose();
          if (obj.material.dispose) obj.material.dispose();
        }
      });
      this.scene.remove(this.fieldModel);
      this.fieldModel = null;
    }

    // Remove field tags
    this.fieldTags.forEach(tag => this.scene.remove(tag));
    this.fieldTags = [];

    // Remove field elements (grid, outline, etc.)
    const toRemove = [];
    this.scene.children.forEach(child => {
      if (child.userData && (child.userData.isFieldElement || child.userData.isCatBox)) {
        toRemove.push(child);
      }
    });
    toRemove.forEach(child => this.scene.remove(child));

    this.fieldConfig = null;
  }

  _makeSprite(text, color) {
    const canvas = document.createElement('canvas');
    canvas.width = 256; canvas.height = 64;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = `#${new THREE.Color(color).getHexString()}`;
    ctx.font = 'bold 24px monospace';
    ctx.textAlign = 'center';
    ctx.fillText(text, 128, 40);
    const tex = new THREE.CanvasTexture(canvas);
    const mat = new THREE.SpriteMaterial({ map: tex });
    const sprite = new THREE.Sprite(mat);
    sprite.scale.set(0.5, 0.125, 1);
    return sprite;
  }

  _setStatus(text) {
    if (this.onStatusChange) this.onStatusChange(text);
    console.log(`[Field] ${text}`);
  }
}
