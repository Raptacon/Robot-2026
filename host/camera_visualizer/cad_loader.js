/**
 * CAD model loader for the robot camera visualizer.
 *
 * Loads GLTF/GLB models, provides transparency control,
 * click-to-select with bounding box and transform output.
 */

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const INCHES_PER_METER = 1 / 0.0254;

export class CadModelManager {
  constructor(scene) {
    this.scene = scene;
    this.model = null;            // THREE.Group — loaded GLTF scene root
    this.meshes = [];             // [{ mesh, originalColor }]
    this.opacity = 0.5;
    this.selectedMesh = null;
    this.selectionBox = null;     // THREE.BoxHelper
    this.showBBox = true;
    this.onSelect = null;         // callback(info) where info = { name, center, size, point }
    this.onStatusChange = null;   // callback(statusText)
    this._loader = new GLTFLoader();
    this._appliedScale = 1.0;
  }

  // ── Loading ──────────────────────────────────────────────────────

  async loadUrl(url) {
    this._setStatus(`Loading ${url.split('/').pop()}...`);
    try {
      const gltf = await this._loader.loadAsync(url);
      this._onGltfLoaded(gltf);
    } catch (e) {
      this._setStatus(`Error: ${e.message}`);
      throw e;
    }
  }

  async loadFile(file) {
    this._setStatus(`Loading ${file.name}...`);
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = async (e) => {
        try {
          const gltf = await this._loader.parseAsync(
            e.target.result, ''
          );
          this._onGltfLoaded(gltf);
          resolve();
        } catch (err) {
          this._setStatus(`Error: ${err.message}`);
          reject(err);
        }
      };
      reader.onerror = () => {
        this._setStatus('Error reading file');
        reject(reader.error);
      };
      reader.readAsArrayBuffer(file);
    });
  }

  _onGltfLoaded(gltf) {
    this.unload();

    const root = gltf.scene;

    // Auto-detect units: if model is way too large, assume inches
    const box = new THREE.Box3().setFromObject(root);
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);

    if (maxDim > 5) {
      // Likely inches — scale to meters
      this._appliedScale = 0.0254;
      root.scale.set(0.0254, 0.0254, 0.0254);
      this._setStatus(`Loaded (auto-scaled from inches)`);
    } else if (maxDim > 1.5) {
      // Likely millimeters
      this._appliedScale = 0.001;
      root.scale.set(0.001, 0.001, 0.001);
      this._setStatus(`Loaded (auto-scaled from mm)`);
    } else {
      this._appliedScale = 1.0;
      this._setStatus('Loaded (meters)');
    }

    // GLTF is Y-up, our scene is Z-up (WPI convention)
    // Rotate so Y-up becomes Z-up: -90deg around X
    root.rotation.x = -Math.PI / 2;

    this.model = root;
    this.scene.add(root);

    // Collect all meshes, make transparent
    this.meshes = [];
    root.traverse((obj) => {
      if (obj.isMesh) {
        // Clone material to avoid mutating shared instances
        obj.material = obj.material.clone();
        const origColor = obj.material.color
          ? obj.material.color.getHex()
          : 0x888888;
        obj.material.transparent = true;
        obj.material.opacity = this.opacity;
        obj.material.depthWrite = this.opacity > 0.9;
        obj.material.side = THREE.DoubleSide;
        this.meshes.push({ mesh: obj, originalColor: origColor });
      }
    });
  }

  // ── Transparency ─────────────────────────────────────────────────

  setOpacity(value) {
    this.opacity = value;
    this.meshes.forEach(({ mesh }) => {
      mesh.material.opacity = value;
      mesh.material.transparent = value < 1.0;
      mesh.material.depthWrite = value > 0.9;
      mesh.material.needsUpdate = true;
    });
  }

  // ── Selection ────────────────────────────────────────────────────

  handleClick(raycaster) {
    if (!this.model || this.meshes.length === 0) return null;

    // Reset previous selection
    if (this.selectedMesh) {
      const prev = this.meshes.find(
        (m) => m.mesh === this.selectedMesh
      );
      if (prev) {
        prev.mesh.material.emissive.setHex(0x000000);
        prev.mesh.material.emissiveIntensity = 0;
      }
    }
    this._removeSelectionBox();

    const targets = this.meshes.map((m) => m.mesh);
    const hits = raycaster.intersectObjects(targets, false);

    if (hits.length === 0) {
      this.selectedMesh = null;
      if (this.onSelect) this.onSelect(null);
      return null;
    }

    const hit = hits[0];
    const mesh = hit.object;
    this.selectedMesh = mesh;

    // Highlight
    mesh.material.emissive.setHex(0xffaa00);
    mesh.material.emissiveIntensity = 0.4;

    // Bounding box
    this._createSelectionBox(mesh);

    // Compute info
    const worldBox = new THREE.Box3().setFromObject(mesh);
    const center = worldBox.getCenter(new THREE.Vector3());
    const bboxSize = worldBox.getSize(new THREE.Vector3());

    // Walk up to find the best name (nearest named parent)
    let name = mesh.name || '';
    if (!name || name.startsWith('mesh') || name.startsWith('Object')) {
      let parent = mesh.parent;
      while (parent && parent !== this.model) {
        if (parent.name && !parent.name.startsWith('Scene')) {
          name = parent.name;
          break;
        }
        parent = parent.parent;
      }
    }
    if (!name) name = '(unnamed)';

    const info = {
      name,
      center,       // THREE.Vector3 in scene meters
      size: bboxSize,
      point: hit.point.clone(),
    };

    if (this.onSelect) this.onSelect(info);
    return info;
  }

  _createSelectionBox(mesh) {
    this.selectionBox = new THREE.BoxHelper(mesh, 0xffaa00);
    this.selectionBox.visible = this.showBBox;
    this.scene.add(this.selectionBox);
  }

  _removeSelectionBox() {
    if (this.selectionBox) {
      this.scene.remove(this.selectionBox);
      this.selectionBox.dispose();
      this.selectionBox = null;
    }
  }

  setShowBBox(show) {
    this.showBBox = show;
    if (this.selectionBox) {
      this.selectionBox.visible = show;
    }
  }

  // ── Cleanup ──────────────────────────────────────────────────────

  unload() {
    this._removeSelectionBox();
    this.selectedMesh = null;

    if (this.model) {
      this.model.traverse((obj) => {
        if (obj.isMesh) {
          obj.geometry.dispose();
          if (obj.material) {
            if (obj.material.map) obj.material.map.dispose();
            obj.material.dispose();
          }
        }
      });
      this.scene.remove(this.model);
      this.model = null;
    }
    this.meshes = [];
  }

  // ── Internal ─────────────────────────────────────────────────────

  _setStatus(text) {
    if (this.onStatusChange) this.onStatusChange(text);
  }
}
